import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";

const apiProxy = process.env.API_PROXY || "http://127.0.0.1:8000";

/** Serve the static catalog at /cars and /cars/, ahead of the SPA fallback. */
function carsPage(): Plugin {
  const rewrite = (url: string | undefined) => {
    const path = url?.split("?")[0];
    if (path === "/cars" || path === "/cars/") return "/cars/index.html";
    return null;
  };
  return {
    name: "cars-page",
    configureServer(server) {
      server.middlewares.use((req, _res, next) => {
        const nextUrl = rewrite(req.url);
        if (nextUrl && req.url) req.url = nextUrl + (req.url.includes("?") ? req.url.slice(req.url.indexOf("?")) : "");
        next();
      });
    },
    configurePreviewServer(server) {
      server.middlewares.use((req, _res, next) => {
        const nextUrl = rewrite(req.url);
        if (nextUrl && req.url) req.url = nextUrl + (req.url.includes("?") ? req.url.slice(req.url.indexOf("?")) : "");
        next();
      });
    },
  };
}

/** Rewrite relative SEO/social URLs to absolute when VITE_SITE_URL is set. */
function absoluteSeoUrls(): Plugin {
  return {
    name: "absolute-seo-urls",
    transformIndexHtml(html) {
      const site = (process.env.VITE_SITE_URL || "").replace(/\/$/, "");
      if (!site) return html;
      return html
        .replaceAll('content="/og-image.png"', `content="${site}/og-image.png"`)
        .replaceAll('content="/"', `content="${site}/"`)
        .replaceAll('href="/"', `href="${site}/"`)
        .replaceAll('"url": "/"', `"url": "${site}/"`);
    },
  };
}

export default defineConfig({
  plugins: [react(), carsPage(), absoluteSeoUrls()],
  server: {
    host: "0.0.0.0",
    port: 5173,
    proxy: {
      "/v1": apiProxy,
      "/health": apiProxy,
      "/sitemap.xml": apiProxy,
    },
  },
});
