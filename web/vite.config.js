import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 开发态 / 预览态同源反代；容器内由 nginx 提供静态文件并把 /api 代理到后端。
const apiTarget = process.env.VITE_PROXY_TARGET || "http://localhost:8000";
const proxy = {
  "/api": {
    target: apiTarget,
    changeOrigin: true,
  },
};

export default defineConfig({
  plugins: [react()],
  server: {
    port: Number(process.env.WEB_PORT || 5173),
    proxy,
  },
  preview: {
    port: Number(process.env.WEB_PORT || 4173),
    proxy,
  },
  test: {
    environment: "jsdom",
    globals: true,
  },
});
