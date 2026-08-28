import { Suspense, lazy } from "react";
import { prefersReducedMotion, supportsWebGL } from "../motion/webgl";
import UpliftQuadrant from "./UpliftQuadrant";
import type { ScatterPoint } from "./PolicySpace";

/** three.js is ~500KB and not everyone can run it.
 *
 * Same three guards as the ambient field, for the same reasons learned the
 * same way: WebGL is absent more often than you would think, an uncaught
 * throw during render unmounts the whole tree, and a browser that will never
 * draw this should not download half a megabyte to find out.
 *
 * The fallback is the flat quadrant rather than an apology. It is the same
 * data minus one axis, which is a real loss and a much smaller one than an
 * empty box where a chart should be.
 */
const PolicySpace = lazy(() => import("./PolicySpace"));

export default function PolicySpaceGuard({ points }: { points: ScatterPoint[] }) {
  if (!supportsWebGL() || prefersReducedMotion()) {
    return (
      <div className="rl-space is-flat">
        <UpliftQuadrant points={points} />
        <p className="rl-space-note">
          Shown flat: this browser has no WebGL, or you have asked for reduced
          motion. The rotatable version adds rupees at risk as a third axis.
        </p>
      </div>
    );
  }
  return (
    <Suspense fallback={<div className="rl-space is-loading" />}>
      <PolicySpace points={points} />
    </Suspense>
  );
}
