import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // 개발 중 /api 요청은 백엔드(4000)로 프록시
      "/api": "http://localhost:4000",
    },
  },
});
