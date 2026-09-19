import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// The Studio talks only to the runtime (CLAUDE.md §4). In dev, Vite proxies /api and /ws to it.
const runtime = process.env.DUCKSTUDIO_RUNTIME ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: runtime, changeOrigin: true },
      "/ws": { target: runtime.replace(/^http/, "ws"), ws: true },
    },
  },
  test: {
    environment: "node",
    include: ["tests/**/*.test.ts"],
  },
});
