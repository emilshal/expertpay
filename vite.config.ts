import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    host: true,
    allowedHosts: [
      "geology-timing-amd-super.trycloudflare.com",
      "ghz-hundreds-efforts-urban.trycloudflare.com",
      "louise-conduct-naturally-addressing.trycloudflare.com",
    ],
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
});
