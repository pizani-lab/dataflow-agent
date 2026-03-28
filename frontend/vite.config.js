import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "0.0.0.0",
    port: 5175,
    proxy: {
      "/api": {
        target: process.env.API_TARGET || "http://localhost:8008",
        changeOrigin: true,
      },
    },
  },
});
