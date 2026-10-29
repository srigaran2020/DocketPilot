import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The built app is served by FastAPI from docketpilot/web/dist. In development, `npm run dev` proxies the API.
const API = "http://127.0.0.1:8000";
const proxied = ["/auth", "/ask", "/cases", "/calendar", "/dashboard", "/matters", "/drafts", "/papers", "/reminders",
  "/search", "/statutes", "/citations", "/chunks", "/acts", "/verify", "/health", "/logo.png"];

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { "@": "/src" } },
  build: { outDir: "../docketpilot/web/dist", emptyOutDir: true, chunkSizeWarningLimit: 900 },
  server: { port: 5173, proxy: Object.fromEntries(proxied.map(p => [p, API])) },
});
