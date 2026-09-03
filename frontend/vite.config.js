import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// La SPA consume la API del backend. En desarrollo se toma de VITE_API_URL
// (.env) o, si no, del proxy /api -> localhost:8000.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: process.env.VITE_API_PROXY || "http://localhost:8000",
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ""),
      },
    },
  },
});
