import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
export default defineConfig({
  plugins: [react()],
  // Production lives under the portfolio domain; keep '/' available for standalone QA.
  base: process.env.VITE_BASE_PATH || "/fourth-down/",
  test: {
    environment: "jsdom",
    setupFiles: "./src/test-setup.ts",
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
