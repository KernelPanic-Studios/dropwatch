import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  // relative asset links: the same build works at / and in a subfolder behind a proxy (issue #5)
  base: "./",
  plugins: [react(), tailwindcss()],
  server: { proxy: { "/api": { target: "http://127.0.0.1:5810", changeOrigin: false } } },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
