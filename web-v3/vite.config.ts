import { defineConfig } from "vite";
import preact from "@preact/preset-vite";

// §73 — an explicit bundle budget, enforced rather than aspirational. The build fails
// (see tools/check_bundle.mjs, run from the deploy workflow) if first-load JS exceeds
// 150 KB gzipped. This app is meant to load on one bar of signal in a boat ramp parking
// lot, which is a real constraint and not a performance nicety.
export default defineConfig({
  plugins: [preact()],
  base: "/app/",
  build: {
    outDir: "dist",
    target: "es2020",
    sourcemap: false,
    reportCompressedSize: true,
    rollupOptions: {
      output: {
        // One chunk. Code-splitting a 40 KB app costs a second round trip on bad signal
        // and saves nothing worth having.
        manualChunks: undefined,
      },
    },
  },
});
