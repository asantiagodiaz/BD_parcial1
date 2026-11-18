import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// En produccion el backend sirve la carpeta dist/ (mismo origen que la API).
// En desarrollo (npm run dev) las rutas de la API se reenvian al backend local.
const API = process.env.VITE_API_PROXY || "http://127.0.0.1:8000";
const proxy = Object.fromEntries(
  ["/flights", "/reservations", "/analytics", "/admin", "/health"].map((p) => [
    p,
    { target: API, changeOrigin: true },
  ])
);

export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy },
});
