import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 3345,
    strictPort: true,
    proxy: {
      "/api/v1": {
        target: "http://127.0.0.1:8001",
        ws: true,
      },
    },
  },
});
