import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import fs from "fs";
import path from "path";

const apiTarget = process.env.VITE_API_BASE || "http://127.0.0.1:8010";

export default defineConfig({
  plugins: [
    react(),
    {
      name: "annotation-data-save",
      configureServer(server) {
        server.middlewares.use("/api/save-annotation", (req, res, next) => {
          if (req.method !== "POST") return next();
          let body = "";
          req.on("data", chunk => { body += chunk; });
          req.on("end", () => {
            try {
              const filePath = path.resolve(__dirname, "public/annotation_data.json");
              fs.writeFileSync(filePath, body, "utf-8");
              res.writeHead(200, { "Content-Type": "application/json" });
              res.end(JSON.stringify({ ok: true }));
            } catch (e) {
              res.writeHead(500, { "Content-Type": "application/json" });
              res.end(JSON.stringify({ ok: false, error: String(e) }));
            }
          });
        });
      }
    }
  ],
  server: {
    port: 5173,
    proxy: {
      "/api": apiTarget
    }
  }
});

