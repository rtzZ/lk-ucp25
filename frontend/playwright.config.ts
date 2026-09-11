import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  use: { baseURL: "http://localhost:5173" },
  webServer: undefined, // серверы поднимаются вручную (см. шапку e2e/cabinet.spec.ts)
});
