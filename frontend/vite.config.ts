import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { resolve } from "path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": resolve(__dirname, "src"),
    },
  },
  server: {
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          // Core React runtime — stable, cached across all routes
          if (id.includes("/node_modules/react/") || id.includes("/node_modules/react-dom/")) {
            return "vendor-react";
          }
          // Routing + data-fetching — cached across all routes
          if (id.includes("/node_modules/@tanstack/react-router")) {
            return "vendor-router";
          }
          if (id.includes("/node_modules/@tanstack/react-query")) {
            return "vendor-query";
          }
          // Heavy one-route deps — only loaded when that route is visited
          if (id.includes("/node_modules/pdfjs-dist/")) {
            return "vendor-pdf";
          }
          if (id.includes("/node_modules/highlight.js/")) {
            return "vendor-highlight";
          }
          if (id.includes("/node_modules/marked/") || id.includes("/node_modules/dompurify/")) {
            return "vendor-markdown";
          }
        },
      },
    },
  },
});
