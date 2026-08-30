import { expect, test } from "@playwright/test";

test("shows a healthy foundation when the API and database respond", async ({ page }) => {
  await page.route("**/api/v1/health/", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ service: "api", status: "ok", database: "ok" }),
    });
  });

  await page.goto("/");

  await expect(page.getByRole("heading", { name: "API connected" })).toBeVisible();
});

