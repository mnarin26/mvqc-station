import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Builds the SPA to the station's static dir so FastAPI serves it.
// In dev, proxy API/WS/stream to the station server on :8000.
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "../station/web",
    emptyOutDir: true,
  },
  server: {
    proxy: {
      "/api": "http://localhost:8000",
      "/stream": "http://localhost:8000",
      "/ws": { target: "ws://localhost:8000", ws: true },
    },
  },
});
