import { useEffect, useRef, useState, type FormEvent } from "react";

import { ApiError, fieldErrors } from "../../api/client";
import { applyRules, createRule, deleteRule, getRules, updateRule } from "../../api/planning";
import type { CategorizationRule, Category, RuleInput } from "../../api/types";
import { useAppAuth } from "../../auth/AuthContext";

type Props = {
  categories: Category[];
  onChanged: (message: string) => void;
  onBusyChange: (busy: boolean) => void;
};

type RuleDraft = Omit<RuleInput, "priority"> & { priority: string };
type Editor = { id: string | null; values: RuleDraft };

function newEditor(categories: Category[]): Editor {
  return {
    id: null,
    values: {
      name: "",
      match_text: "",
      priority: "100",
      category: categories.find((category) => category.is_active)?.id ?? "",
      is_active: true,
    },
  };
}

export function RulesPanel({ categories, onChanged, onBusyChange }: Props) {
  const { transport, invalidate } = useAppAuth();
  const [rules, setRules] = useState<CategorizationRule[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [refresh, setRefresh] = useState(0);
  const [editor, setEditor] = useState<Editor | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [confirmApply, setConfirmApply] = useState(false);
  const [busy, setBusy] = useState(false);
  const mounted = useRef(true);
  const inFlight = useRef(false);
  const operation = useRef(0);
  const formRef = useRef<HTMLFormElement>(null);
  const editorOpen = editor !== null;
  const editingId = editor?.id;
  const activeCategories = categories.filter((category) => category.is_active);
  const currentRule = rules?.find((rule) => rule.id === editor?.id);
  const availableCategories = categories.filter(
    (category) => category.is_active || category.id === currentRule?.category,
  );
  const eligibleRules =
    rules?.filter(
      (rule) =>
        rule.is_active &&
        categories.some((category) => category.id === rule.category && category.is_active),
    ) ?? [];
  const actionsDisabled = busy || loading || rules === null;

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      operation.current += 1;
      inFlight.current = false;
      onBusyChange(false);
    };
  }, [onBusyChange]);

  useEffect(() => {
    if (editorOpen) formRef.current?.focus();
  }, [editorOpen, editingId]);

  useEffect(() => {
    if (!transport) {
      setLoading(false);
      setRules(null);
      return;
    }
    const controller = new AbortController();
    let active = true;
    setLoading(true);
    setLoadError(null);
    setRules(null);
    getRules(transport, controller.signal)
      .then((result) => {
        if (!active) return;
        setRules(
          [...result].sort(
            (left, right) =>
              left.priority - right.priority ||
              left.created_at.localeCompare(right.created_at) ||
              left.id.localeCompare(right.id),
          ),
        );
      })
      .catch((requestError: unknown) => {
        if (!active || (requestError instanceof DOMException && requestError.name === "AbortError"))
          return;
        if (requestError instanceof ApiError && requestError.status === 401) {
          void invalidate();
        } else {
          setLoadError(
            requestError instanceof Error ? requestError.message : "Unable to load rules.",
          );
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [transport, invalidate, refresh]);

  function reloadRules() {
    setLoading(true);
    setRules(null);
    setRefresh((current) => current + 1);
  }

  function openEditor(rule?: CategorizationRule) {
    if (actionsDisabled || inFlight.current) return;
    setEditor(
      rule
        ? {
            id: rule.id,
            values: {
              name: rule.name,
              match_text: rule.match_text,
              priority: String(rule.priority),
              category: rule.category,
              is_active: rule.is_active,
            },
          }
        : newEditor(categories),
    );
    setDeletingId(null);
    setConfirmApply(false);
    setErrors({});
    setError(null);
  }

  function changeField<Key extends keyof RuleDraft>(field: Key, value: RuleDraft[Key]) {
    setEditor((current) =>
      current ? { ...current, values: { ...current.values, [field]: value } } : current,
    );
    setErrors((current) => ({ ...current, [field]: "" }));
  }

  async function mutate(action: () => Promise<string>, fallback: string, afterSuccess: () => void) {
    if (inFlight.current || actionsDisabled) return;
    if (!transport) {
      setError("Your session has expired. Sign in again.");
      return;
    }
    inFlight.current = true;
    const generation = ++operation.current;
    setBusy(true);
    onBusyChange(true);
    setError(null);
    setErrors({});
    try {
      const message = await action();
      if (!mounted.current || operation.current !== generation) return;
      afterSuccess();
      reloadRules();
      onChanged(message);
    } catch (requestError: unknown) {
      if (!mounted.current || operation.current !== generation) return;
      if (requestError instanceof ApiError && requestError.status === 401) {
        await invalidate();
      } else {
        const backendErrors = fieldErrors(requestError);
        setErrors(backendErrors);
        setError(
          ["name", "match_text", "priority", "category", "is_active"].some(
            (field) => backendErrors[field],
          )
            ? "Review the highlighted fields."
            : (backendErrors.non_field_errors ??
                (requestError instanceof Error ? requestError.message : fallback)),
        );
      }
    } finally {
      if (mounted.current && operation.current === generation) {
        inFlight.current = false;
        setBusy(false);
        onBusyChange(false);
      }
    }
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!editor || !transport || actionsDisabled || inFlight.current) return;
    const values = editor.values;
    const nextErrors: Record<string, string> = {};
    if (!values.name.trim()) nextErrors.name = "Enter a rule name.";
    if (!values.match_text.trim())
      nextErrors.match_text = "Enter text to match in the description.";
    if (
      !/^\d+$/.test(values.priority) ||
      Number(values.priority) < 1 ||
      Number(values.priority) > 9999
    )
      nextErrors.priority = "Enter a whole number from 1 to 9999.";
    if (
      !availableCategories.some(
        (category) =>
          category.id === values.category &&
          (category.is_active || category.id === currentRule?.category),
      )
    )
      nextErrors.category = "Choose an active category.";
    if (Object.keys(nextErrors).length > 0) {
      setErrors(nextErrors);
      setError("Review the highlighted fields.");
      return;
    }
    const payload: RuleInput = {
      ...values,
      name: values.name.trim(),
      match_text: values.match_text.trim(),
      priority: Number(values.priority),
    };
    await mutate(
      async () => {
        if (editor.id) {
          await updateRule(transport, editor.id, payload);
          return `Saved rule ${payload.name}.`;
        }
        await createRule(transport, payload);
        return `Created rule ${payload.name}.`;
      },
      "Unable to save this rule.",
      () => setEditor(null),
    );
  }

  async function toggleRule(rule: CategorizationRule) {
    if (!transport) return;
    await mutate(
      async () => {
        await updateRule(transport, rule.id, { is_active: !rule.is_active });
        return `${rule.is_active ? "Disabled" : "Enabled"} rule ${rule.name}.`;
      },
      "Unable to update this rule.",
      () => {
        setDeletingId(null);
        setConfirmApply(false);
      },
    );
  }

  async function removeRule(rule: CategorizationRule) {
    if (!transport) return;
    await mutate(
      async () => {
        await deleteRule(transport, rule.id);
        return `Deleted rule ${rule.name}. Existing transaction categories were preserved.`;
      },
      "Unable to delete this rule.",
      () => setDeletingId(null),
    );
  }

  async function applyToTransactions() {
    if (!transport || !confirmApply) return;
    await mutate(
      async () => {
        const result = await applyRules(transport);
        return `Categorized ${result.updated} ${result.updated === 1 ? "transaction" : "transactions"}. Reviewed ${result.examined} uncategorized ${result.examined === 1 ? "transaction" : "transactions"}.`;
      },
      "Unable to apply rules. You can safely retry this action.",
      () => setConfirmApply(false),
    );
  }

  function fieldError(field: keyof RuleDraft) {
    return errors[field] ? (
      <span className="field-error" id={`rule-${field}-error`}>
        {errors[field]}
      </span>
    ) : null;
  }

  return (
    <section
      className="transaction-panel"
      aria-labelledby="rules-heading"
      aria-busy={busy || loading}
    >
      <div className="panel-heading">
        <div>
          <p className="card-kicker">Automatic categories</p>
          <h2 id="rules-heading">Categorization rules</h2>
        </div>
        <div className="resource-actions">
          <button
            className="secondary-button"
            type="button"
            disabled={actionsDisabled || editorOpen || eligibleRules.length === 0}
            onClick={() => {
              setConfirmApply(true);
              setDeletingId(null);
              setError(null);
              setErrors({});
            }}
          >
            Apply rules
          </button>
          <button
            className="primary-button"
            type="button"
            disabled={actionsDisabled || editorOpen || activeCategories.length === 0}
            onClick={() => openEditor()}
          >
            Add rule
          </button>
        </div>
      </div>
      <p>
        Match description text to a category, ignoring letter case. The first enabled rule wins:
        lower priority numbers run first, with older rules first when priorities match.
      </p>
      <p className="muted">
        New transactions and CSV imports use your current rules. Saving a rule does not change
        existing transactions. Apply rules only fills transactions still set to automatic with no
        category; manual choices and previous rule assignments are preserved.
      </p>
      {activeCategories.length === 0 ? (
        <p className="notice">Create or restore a category in Categories to add a rule.</p>
      ) : null}
      {error ? (
        <p className="form-error" role="alert">
          {error}
        </p>
      ) : null}

      {editor ? (
        <form
          ref={formRef}
          tabIndex={-1}
          onSubmit={save}
          noValidate
          aria-labelledby="rule-form-heading"
        >
          <h3 id="rule-form-heading">{editor.id ? "Edit rule" : "Add rule"}</h3>
          <div className="form-grid">
            <label>
              Rule name
              <input
                aria-label="Rule name"
                value={editor.values.name}
                onChange={(event) => changeField("name", event.target.value)}
                maxLength={100}
                disabled={busy}
                aria-invalid={Boolean(errors.name)}
                aria-describedby={errors.name ? "rule-name-error" : undefined}
              />
              {fieldError("name")}
            </label>
            <label>
              Description contains
              <input
                aria-label="Description contains"
                value={editor.values.match_text}
                onChange={(event) => changeField("match_text", event.target.value)}
                maxLength={100}
                disabled={busy}
                aria-invalid={Boolean(errors.match_text)}
                aria-describedby={errors.match_text ? "rule-match_text-error" : undefined}
              />
              {fieldError("match_text")}
            </label>
            <label>
              Rule priority
              <input
                aria-label="Rule priority"
                type="number"
                min={1}
                max={9999}
                step={1}
                value={editor.values.priority}
                onChange={(event) => changeField("priority", event.target.value)}
                disabled={busy}
                aria-invalid={Boolean(errors.priority)}
                aria-describedby={errors.priority ? "rule-priority-error" : "rule-priority-help"}
              />
              <span className="muted" id="rule-priority-help">
                Lower numbers match first.
              </span>
              {fieldError("priority")}
            </label>
            <label>
              Rule category
              <select
                aria-label="Rule category"
                value={editor.values.category}
                onChange={(event) => changeField("category", event.target.value)}
                disabled={busy}
                aria-invalid={Boolean(errors.category)}
                aria-describedby={errors.category ? "rule-category-error" : undefined}
              >
                <option value="">Choose a category</option>
                {availableCategories.map((category) => (
                  <option key={category.id} value={category.id}>
                    {category.name}
                    {category.is_active ? "" : " (archived, current)"}
                  </option>
                ))}
              </select>
              {fieldError("category")}
            </label>
            <label className="rule-enabled">
              <input
                type="checkbox"
                aria-label="Rule enabled"
                checked={editor.values.is_active}
                onChange={(event) => changeField("is_active", event.target.checked)}
                disabled={busy}
                aria-invalid={Boolean(errors.is_active)}
                aria-describedby={errors.is_active ? "rule-is_active-error" : undefined}
              />
              Rule enabled
              {fieldError("is_active")}
            </label>
          </div>
          {currentRule &&
          !categories.find((category) => category.id === currentRule.category)?.is_active ? (
            <p className="notice">
              This rule currently points to an archived category and is skipped until the category
              is restored or an active category is selected.
            </p>
          ) : null}
          <div className="form-actions">
            <button
              className="text-button"
              type="button"
              disabled={busy}
              onClick={() => {
                setEditor(null);
                setErrors({});
                setError(null);
              }}
            >
              Cancel
            </button>
            <button className="primary-button" type="submit" disabled={actionsDisabled}>
              {busy ? "Saving…" : editor.id ? "Save rule" : "Create rule"}
            </button>
          </div>
        </form>
      ) : null}

      {confirmApply ? (
        <div className="confirm-panel" role="group" aria-label="Confirm applying rules">
          <h3>Apply rules to existing transactions?</h3>
          <p>
            Fill automatic transactions that have no category using the first matching enabled rule.
            Manual choices and transactions already categorized by a rule will stay as they are.
            Rules with archived categories are skipped.
          </p>
          <div className="resource-actions">
            <button
              className="primary-button"
              type="button"
              disabled={actionsDisabled || eligibleRules.length === 0}
              onClick={() => void applyToTransactions()}
            >
              {busy ? "Applying…" : "Confirm apply"}
            </button>
            <button
              className="text-button"
              type="button"
              disabled={busy}
              onClick={() => {
                setConfirmApply(false);
                setError(null);
              }}
            >
              Cancel
            </button>
          </div>
        </div>
      ) : null}

      {loading ? <p className="notice">Loading rules…</p> : null}
      {loadError ? (
        <div className="error-banner" role="alert">
          <p>{loadError}</p>
          <button className="secondary-button" type="button" onClick={reloadRules} disabled={busy}>
            Retry rules
          </button>
        </div>
      ) : null}
      {!loading && rules?.length === 0 ? (
        <p className="notice">
          Add your first rule, such as descriptions containing “market” for Groceries. Matching uses
          literal text, so punctuation and spaces matter.
        </p>
      ) : null}
      {!loading && rules && rules.length > 0 ? (
        <ol className="rule-list">
          {rules.map((rule, index) => {
            const category = categories.find((item) => item.id === rule.category);
            const skipped = !category?.is_active;
            return (
              <li className="resource-card" key={rule.id}>
                <div className="rule-details">
                  <span className="rule-position" aria-label={`Match order ${index + 1}`}>
                    {index + 1}
                  </span>
                  <div>
                    <h3>{rule.name}</h3>
                    <p className="resource-meta">
                      Priority {rule.priority} · {rule.is_active ? "Enabled" : "Disabled"}
                      {skipped ? " · Archived category, skipped" : ""}
                    </p>
                    <p className="rule-match">
                      Contains <strong>{rule.match_text}</strong> → {rule.category_name}
                    </p>
                  </div>
                </div>
                <div className="resource-actions">
                  <button
                    className="secondary-button"
                    type="button"
                    aria-label={`Edit rule ${rule.name}`}
                    disabled={actionsDisabled || editorOpen}
                    onClick={() => openEditor(rule)}
                  >
                    Edit
                  </button>
                  <button
                    className="secondary-button"
                    type="button"
                    aria-label={`${rule.is_active ? "Disable" : "Enable"} rule ${rule.name}`}
                    disabled={actionsDisabled || editorOpen}
                    onClick={() => void toggleRule(rule)}
                  >
                    {rule.is_active ? "Disable" : "Enable"}
                  </button>
                  <button
                    className="danger-button"
                    type="button"
                    aria-label={`Delete rule ${rule.name}`}
                    disabled={actionsDisabled || editorOpen}
                    onClick={() => {
                      setDeletingId(rule.id);
                      setConfirmApply(false);
                      setError(null);
                    }}
                  >
                    Delete
                  </button>
                </div>
                {deletingId === rule.id ? (
                  <div
                    className="confirm-panel"
                    role="group"
                    aria-label={`Confirm deletion of rule ${rule.name}`}
                  >
                    <p>
                      Delete {rule.name}? Existing transaction categories will be preserved. New
                      transactions will no longer use this rule.
                    </p>
                    <div className="resource-actions">
                      <button
                        className="danger-button"
                        type="button"
                        disabled={actionsDisabled}
                        onClick={() => void removeRule(rule)}
                      >
                        Confirm delete
                      </button>
                      <button
                        className="text-button"
                        type="button"
                        disabled={busy}
                        onClick={() => {
                          setDeletingId(null);
                          setError(null);
                        }}
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                ) : null}
              </li>
            );
          })}
        </ol>
      ) : null}
    </section>
  );
}
