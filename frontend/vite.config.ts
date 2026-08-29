import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Built to ../dashboard/dist so the compiled app lives beside the Python that
// generates its data. `base: "./"` keeps every asset path relative, so the
// build opens correctly from the filesystem and from any subpath on GitHub
// Pages without reconfiguration.
export default defineConfig({
  plugins: [react()],
  base: "./",
  // emptyOutDir is off because `dashboard/dist` is not exclusively Vite's:
  // `build_dashboard.py` writes data.json there, and that file is the entire
  // content of the page. With emptying on, running `npm run build` (or `make
  // frontend-build`) after `make dashboard` deleted it and left a shell that
  // fetches a 404 and renders nothing — no build error, no console error until
  // the page is opened. `make dashboard` depends on frontend-build and so
  // always regenerated it, which is why this only bit when the build was run
  // on its own. Asset filenames are content-hashed, so not emptying leaves
  // superseded chunks behind rather than serving them.
  build: { outDir: "../dashboard/dist", emptyOutDir: false },
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
