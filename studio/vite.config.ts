import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// The Studio talks only to the runtime (CLAUDE.md §4). In dev, Vite proxies /api and /ws to it.
const runtime = process.env.DUCKSTUDIO_RUNTIME ?? "http://127.0.0.1:8000";

const proxy = {
  "/api": { target: runtime, changeOrigin: true },
  "/ws": { target: runtime.replace(/^http/, "ws"), ws: true },
};

export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy },
  // `pnpm preview` serves the built Studio and needs the same proxy — that is what the smoke
  // test runs against, in CI and here.
  preview: { port: 4173, proxy },
  test: {
    environment: "node",
    include: ["tests/**/*.test.ts"],
  },
});
