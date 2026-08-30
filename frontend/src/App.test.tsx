import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import App from "./App";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("App", () => {
  it("shows a connected state after the API health check succeeds", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ service: "api", status: "ok", database: "ok" }),
      }),
    );

    render(<App />);

    expect(screen.getByText("Checking services")).toBeInTheDocument();
    expect(await screen.findByText("API connected")).toBeInTheDocument();
  });

  it("shows an unavailable state when the API health check fails", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("network unavailable")));

    render(<App />);

    expect(await screen.findByText("Connection unavailable")).toBeInTheDocument();
  });
});

