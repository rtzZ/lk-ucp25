import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: { port: 5173 },
  build: {
    rollupOptions: {
      output: {
        // Atlaskit тянет ~0.9 МБ: отдельным чанком, чтобы код приложения
        // инвалидировался независимо от вендора.
        manualChunks(id) {
          if (id.includes("node_modules")) {
            if (id.includes("@atlaskit")) return "atlaskit";
            return "vendor";
          }
        },
      },
    },
  },
});
