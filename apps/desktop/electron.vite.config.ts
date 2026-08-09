import { resolve } from "node:path";
import { defineConfig, externalizeDepsPlugin } from "electron-vite";
import react from "@vitejs/plugin-react";

const sharedAlias = { "@shared": resolve(__dirname, "src/shared") };

export default defineConfig({
  main: {
    resolve: { alias: sharedAlias },
    plugins: [externalizeDepsPlugin()],
    build: {
      rollupOptions: {
        input: { index: resolve(__dirname, "src/main/index.ts") },
      },
    },
  },
  preload: {
    resolve: { alias: sharedAlias },
    plugins: [externalizeDepsPlugin()],
    build: {
      rollupOptions: {
        input: { index: resolve(__dirname, "src/preload/index.ts") },
      },
    },
  },
  renderer: {
    root: "src/renderer",
    resolve: { alias: sharedAlias },
    build: {
      rollupOptions: {
        input: { index: resolve(__dirname, "src/renderer/index.html") },
      },
    },
    plugins: [react()],
  },
});
