import { Suspense, lazy, useEffect } from "react";
import { prefersReducedMotion, supportsWebGL } from "../motion/webgl";

/** The ambient environment, fixed behind the whole document.
 *
 * Not boxed into the hero: this system watches a payment fleet continuously,
 * so the field should feel like it is always running underneath, not like an
 * illustration parked at the top of the page.
 *
 * Three guards, all learned the hard way:
 *   · supportsWebGL() runs before the import, because THREE's renderer throws
 *     when no context exists and an uncaught error during React render
 *     unmounts the entire tree — a decorative background was once able to
 *     blank the whole dashboard on machines with no hardware acceleration.
 *   · the import is lazy, so browsers that will never draw it don't pay for
 *     three.js.
 *   · reduced-motion gets the static gradient. Nothing here is information the
 *     page states only in the field.
 */
const FleetField = lazy(() => import("./FleetField"));

export default function Scene({ litFraction }: { litFraction: number }) {
  const still = !supportsWebGL() || prefersReducedMotion();

  // The shader dims itself past the first screen (see FleetField's uCalm). The
  // static stand-in has no shader, so the same recession is published as a CSS
  // variable and applied to its opacity — otherwise a fixed grid sits at full
  // strength behind every dense table further down the page.
  useEffect(() => {
    if (!still) return;
    let raf = 0;
    const set = () => {
      raf = 0;
      const calm = 1 - Math.min(window.scrollY / (window.innerHeight * 1.15), 1) * 0.72;
      document.documentElement.style.setProperty("--rl-calm", calm.toFixed(3));
    };
    const onScroll = () => { if (!raf) raf = requestAnimationFrame(set); };
    set();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      window.removeEventListener("scroll", onScroll);
      cancelAnimationFrame(raf);
      document.documentElement.style.removeProperty("--rl-calm");
    };
  }, [still]);

  if (still) {
    return <div className="rl-scene rl-scene--static" aria-hidden="true" />;
  }
  return (
    <div className="rl-scene" aria-hidden="true">
      <Suspense fallback={<div className="rl-scene--static" style={{ position: "absolute", inset: 0 }} />}>
        <FleetField litFraction={litFraction} />
      </Suspense>
    </div>
  );
}
