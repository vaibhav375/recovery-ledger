/** Can this browser actually give us a WebGL context?
 *
 * Checked before importing anything from three.js, for two reasons:
 *
 * 1. ThreeUI's shader components construct a `THREE.WebGLRenderer` during
 *    render, and that constructor THROWS when no context is available. An
 *    uncaught error thrown during React render unmounts the whole tree — so a
 *    purely decorative background was able to blank the entire dashboard on
 *    machines with hardware acceleration disabled or a blocklisted GPU.
 * 2. When WebGL is unavailable the ~500KB three.js chunk is pure waste, so
 *    this also avoids downloading it.
 *
 * Result is cached: creating throwaway contexts is not free, and browsers cap
 * how many can exist at once.
 */
let cached: boolean | null = null;

export function supportsWebGL(): boolean {
  if (cached !== null) return cached;
  if (typeof document === "undefined") return (cached = false);
  try {
    const canvas = document.createElement("canvas");
    const gl =
      canvas.getContext("webgl2") ??
      canvas.getContext("webgl") ??
      canvas.getContext("experimental-webgl");
    cached = Boolean(gl);
    // Release it immediately rather than holding a context we don't need.
    const lose = (gl as WebGLRenderingContext | null)?.getExtension("WEBGL_lose_context");
    lose?.loseContext();
  } catch {
    cached = false;
  }
  return cached;
}

export function prefersReducedMotion(): boolean {
  return (
    typeof window !== "undefined" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}
