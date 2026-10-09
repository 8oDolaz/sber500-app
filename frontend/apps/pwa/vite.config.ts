import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import { VitePWA } from "vite-plugin-pwa";

const API_TARGET = process.env.KAINEM_API ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: "autoUpdate",
      includeAssets: ["favicon.svg", "favicon.ico", "apple-touch-icon-180x180.png"],
      manifest: {
        name: "kainem",
        short_name: "kainem",
        description: "Семейный помощник",
        lang: "ru",
        start_url: "/",
        scope: "/",
        display: "standalone",
        orientation: "portrait",
        background_color: "#ffffff",
        theme_color: "#ffffff",
        icons: [
          { src: "pwa-192x192.png", sizes: "192x192", type: "image/png" },
          { src: "pwa-512x512.png", sizes: "512x512", type: "image/png" },
          { src: "maskable-icon-512x512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
        ],
      },
      workbox: {
        navigateFallback: "/index.html",
        // The API and bot webhooks must never be served from the SW cache; Grafana (served by Caddy) is not the app.
        navigateFallbackDenylist: [/^\/api\//, /^\/grafana(\/|$)/],
        globPatterns: ["**/*.{js,css,html,svg,png,woff2}"],
        // Russian UI: precache only Latin/Cyrillic Inter; other subsets load on demand via unicode-range.
        globIgnores: ["**/inter-{greek,greek-ext,vietnamese}-*.woff2"],
      },
    }),
  ],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: API_TARGET, changeOrigin: true, rewrite: (p) => p.replace(/^\/api/, "") },
    },
  },
});
