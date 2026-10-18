import { useEffect, useRef, useState, type FormEvent } from "react";

import { ApiError, fieldErrors } from "../../api/client";
import type { Category, CategoryInput } from "../../api/types";

type Props = {
  categories: Category[];
  onCreate: (payload: CategoryInput) => Promise<void>;
  onUpdate: (id: string, payload: Partial<CategoryInput & { is_active: boolean }>) => Promise<void>;
  onDelete: (id: string) => Promise<void>;
};

type Editor = { id: string | null; values: CategoryInput };

const categoryKinds: { value: Category["kind"]; label: string }[] = [
  { value: "expense", label: "Expense" },
  { value: "income", label: "Income" },
  { value: "transfer", label: "Transfer" },
];

function newEditor(): Editor {
  return { id: null, values: { name: "", kind: "expense" } };
}

export function CategoryManager({ categories, onCreate, onUpdate, onDelete }: Props) {
  const [editor, setEditor] = useState<Editor | null>(() =>
    categories.length === 0 ? newEditor() : null,
  );
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const formRef = useRef<HTMLFormElement>(null);
  const editorOpen = editor !== null;
  const editingId = editor?.id;

  useEffect(() => {
    if (editorOpen) formRef.current?.focus();
  }, [editorOpen, editingId]);

  useEffect(() => {
    if (categories.length === 0) {
      setEditor((current) => (current && !current.id ? current : newEditor()));
    }
  }, [categories.length]);

  function openEditor(category?: Category) {
    if (busy) return;
    setEditor(
      category
        ? {
            id: category.id,
            values: { name: category.name, kind: category.kind },
          }
        : newEditor(),
    );
    setDeletingId(null);
    setErrors({});
    setError(null);
  }

  function changeField<Key extends keyof CategoryInput>(field: Key, value: CategoryInput[Key]) {
    setEditor((current) =>
      current
        ? {
            ...current,
            values: { ...current.values, [field]: value },
          }
        : current,
    );
    setErrors((current) => ({ ...current, [field]: "" }));
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!editor || busy) return;
    const payload = { ...editor.values, name: editor.values.name.trim() };
    if (!payload.name) {
      setErrors({ name: "Enter a category name." });
      setError("Review the highlighted fields.");
      return;
    }
    setBusy(true);
    setError(null);
    setErrors({});
    try {
      if (editor.id) {
        await onUpdate(editor.id, payload);
      } else {
        await onCreate(payload);
      }
      setEditor(null);
    } catch (requestError: unknown) {
      const backendErrors = fieldErrors(requestError);
      setErrors(backendErrors);
      setError(
        backendErrors.name || backendErrors.kind
          ? "Review the highlighted fields."
          : (backendErrors.non_field_errors ??
              (requestError instanceof Error ? requestError.message : "Unable to save category.")),
      );
    } finally {
      setBusy(false);
    }
  }

  async function toggleActive(category: Category) {
    if (busy) return;
    setBusy(true);
    setError(null);
    setDeletingId(null);
    try {
      await onUpdate(category.id, { is_active: !category.is_active });
    } catch (requestError: unknown) {
      setError(requestError instanceof Error ? requestError.message : "Unable to update category.");
    } finally {
      setBusy(false);
    }
  }

  async function deleteCategory(category: Category) {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      await onDelete(category.id);
      setDeletingId(null);
      setEditor((current) => (current?.id === category.id ? null : current));
    } catch (requestError: unknown) {
      setError(
        requestError instanceof ApiError && requestError.status === 409
          ? `${requestError.message} ${category.is_active ? "Archive this category" : "Keep this category archived"} to preserve its transaction history.`
          : requestError instanceof Error
            ? requestError.message
            : "Unable to delete category.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <section
      className="transaction-panel"
      aria-labelledby="category-manager-heading"
      aria-busy={busy}
    >
      <div className="panel-heading">
        <div>
          <p className="card-kicker">Transaction categories</p>
          <h2 id="category-manager-heading">Categories</h2>
        </div>
        <button
          className="primary-button"
          type="button"
          onClick={() => openEditor()}
          disabled={busy}
        >
          Add category
        </button>
      </div>

      {error ? (
        <p className="form-error" role="alert">
          {error}
        </p>
      ) : null}

      {editor ? (
        <form ref={formRef} tabIndex={-1} onSubmit={save} aria-labelledby="category-form-heading">
          <h3 id="category-form-heading">{editor.id ? "Edit category" : "Add category"}</h3>
          <div className="form-grid">
            <label>
              Category name
              <input
                aria-label="Category name"
                value={editor.values.name}
                onChange={(event) => changeField("name", event.target.value)}
                maxLength={100}
                disabled={busy}
                aria-invalid={Boolean(errors.name)}
                aria-describedby={errors.name ? "category-name-error" : undefined}
              />
              {errors.name ? (
                <span className="field-error" id="category-name-error">
                  {errors.name}
                </span>
              ) : null}
            </label>
            <label>
              Category kind
              <select
                aria-label="Category kind"
                value={editor.values.kind}
                onChange={(event) => changeField("kind", event.target.value as Category["kind"])}
                disabled={busy}
                aria-invalid={Boolean(errors.kind)}
                aria-describedby={errors.kind ? "category-kind-error" : undefined}
              >
                {categoryKinds.map((kind) => (
                  <option key={kind.value} value={kind.value}>
                    {kind.label}
                  </option>
                ))}
              </select>
              {errors.kind ? (
                <span className="field-error" id="category-kind-error">
                  {errors.kind}
                </span>
              ) : null}
            </label>
          </div>
          <div className="form-actions">
            <button
              className="text-button"
              type="button"
              onClick={() => {
                setEditor(null);
                setErrors({});
                setError(null);
              }}
              disabled={busy}
            >
              Cancel
            </button>
            <button className="primary-button" type="submit" disabled={busy}>
              {busy ? "Saving…" : editor.id ? "Save category" : "Create category"}
            </button>
          </div>
        </form>
      ) : null}

      {categories.length === 0 ? (
        <p className="notice">
          Create categories for expenses, income, or transfers. Transactions can also remain
          uncategorized.
        </p>
      ) : (
        <div className="resource-grid">
          {categories.map((category) => (
            <article className="resource-card" key={category.id}>
              <h3>{category.name}</h3>
              <p className="resource-meta">
                {categoryKinds.find((kind) => kind.value === category.kind)?.label} ·{" "}
                {category.is_active ? "Active" : "Archived"}
              </p>
              <div className="resource-actions">
                <button
                  className="secondary-button"
                  type="button"
                  aria-label={`Edit category ${category.name}`}
                  onClick={() => openEditor(category)}
                  disabled={busy}
                >
                  Edit
                </button>
                <button
                  className="secondary-button"
                  type="button"
                  aria-label={`${category.is_active ? "Archive" : "Restore"} category ${category.name}`}
                  onClick={() => void toggleActive(category)}
                  disabled={busy}
                >
                  {category.is_active ? "Archive" : "Restore"}
                </button>
                <button
                  className="danger-button"
                  type="button"
                  aria-label={`Delete category ${category.name}`}
                  onClick={() => {
                    setDeletingId(category.id);
                    setError(null);
                  }}
                  disabled={busy}
                >
                  Delete
                </button>
              </div>
              {deletingId === category.id ? (
                <div
                  className="confirm-panel"
                  role="group"
                  aria-label={`Confirm deletion of category ${category.name}`}
                >
                  <p>
                    Delete {category.name}? Only categories without transactions can be deleted.
                    Archive a category to preserve its history.
                  </p>
                  <div className="resource-actions">
                    <button
                      className="danger-button"
                      type="button"
                      onClick={() => void deleteCategory(category)}
                      disabled={busy}
                    >
                      Confirm delete
                    </button>
                    <button
                      className="text-button"
                      type="button"
                      onClick={() => {
                        setDeletingId(null);
                        setError(null);
                      }}
                      disabled={busy}
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              ) : null}
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
