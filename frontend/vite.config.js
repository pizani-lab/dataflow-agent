import {defineConfig} from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
    plugins: [react()],
    server: {
        host: "0.0.0.0",
        port: 5101,
        proxy: {
            allowedHosts: ["*.pizani.ia.br", "localhost", "*"],
            "/api": {
                target: process.env.API_TARGET || "https://api-dataflow.pizani.ia.br", changeOrigin: true,
            },
        },
    },
});
