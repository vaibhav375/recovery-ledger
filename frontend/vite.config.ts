import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Built to ../dashboard/dist so the compiled app lives beside the Python that
// generates its data. `base: "./"` keeps every asset path relative, so the
// build opens correctly from the filesystem and from any subpath on GitHub
// Pages without reconfiguration.
export default defineConfig({
  plugins: [react()],
  base: "./",
  build: { outDir: "../dashboard/dist", emptyOutDir: true },
  // `npm run dev` serves the app from Vite, but the live console's API and
  // its SSE stream come from the Python server on 5175. Proxying keeps them
  // same-origin in development, exactly as they are in the built app that
  // server also serves. `changeOrigin` off and buffering unset on purpose:
  // /api/stream is Server-Sent Events and must not be buffered.
  server: {
    proxy: {
      "/api": { target: "http://localhost:5175", changeOrigin: false },
    },
  },
});
