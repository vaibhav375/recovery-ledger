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
});
