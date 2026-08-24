import { useEffect, useRef } from "react";
import * as THREE from "three";

/** The ambient field: a real three.js scene, written for this project.
 *
 * ThreeUI ships shader backgrounds (TopoField and friends), and the first
 * version of this page used one. They are rendered inside a sandboxed iframe
 * whose srcdoc pulls Tailwind from `cdn.tailwindcss.com` at runtime — which
 * means a network dependency in a dashboard meant to run offline from a static
 * `dist/`, and an opaque document that cannot be tinted, blended, or driven by
 * the page's own data. ThreeUI's token system and stylesheet still shape this
 * UI; only the background is ours.
 *
 * What it draws is not decoration. The wireframe is the fleet: a lattice of
 * payment cases on a plane that swells slowly beneath the camera. The lit
 * nodes standing on it are the holdout — exactly `litFraction` of them, the
 * measured no-contact recovery rate from data.json, the share of cases that
 * resolve without the agent ever speaking. They are picked by an exact
 * stratified draw rather than a per-node coin flip, so the count on screen is
 * the rate, not an approximation of it.
 *
 * That is the whole argument of the project, running quietly underneath it.
 */
export default function FleetField({ litFraction }: { litFraction: number }) {
  const host = useRef<HTMLDivElement>(null);
  const lit = useRef(litFraction);
  lit.current = litFraction;

  useEffect(() => {
    const el = host.current;
    if (!el) return;

    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: false, alpha: true, powerPreference: "low-power" });
    } catch {
      return; // Guarded upstream too; a background must never break the page.
    }

    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.75));
    renderer.setClearColor(0x000000, 0);
    el.appendChild(renderer.domElement);

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(52, 1, 1, 400);
    camera.position.set(0, 27, 40);
    camera.lookAt(0, 0, -48);

    // ── the fleet ────────────────────────────────────────────────────────
    const STEP = 3.1;
    const XS = 92, ZS = 78;
    const N = XS * ZS;
    const pos = new Float32Array(N * 3);
    const rand = new Float32Array(N);
    const phase = new Float32Array(N);

    // Exact stratified draw: rank r/N shuffled across points, so `step(rank,
    // litFraction)` lights precisely floor(N · litFraction) of them. A plain
    // Math.random() per point would only get there in expectation.
    const ranks = new Float32Array(N);
    for (let i = 0; i < N; i++) ranks[i] = i / N;
    for (let i = N - 1; i > 0; i--) {
      const j = (Math.random() * (i + 1)) | 0;
      const t = ranks[i]; ranks[i] = ranks[j]; ranks[j] = t;
    }

    for (let i = 0; i < N; i++) {
      const ix = i % XS, iz = (i / XS) | 0;
      pos[i * 3] = (ix - XS / 2) * STEP;
      pos[i * 3 + 1] = 0;
      pos[i * 3 + 2] = -iz * STEP + 30;
      rand[i] = ranks[i];
      phase[i] = Math.random();
    }

    const aPos = new THREE.BufferAttribute(pos, 3);
    const aRank = new THREE.BufferAttribute(rand, 1);
    const aPhase = new THREE.BufferAttribute(phase, 1);

    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", aPos);
    geo.setAttribute("aRank", aRank);
    geo.setAttribute("aPhase", aPhase);

    // The lattice itself, as line segments over the same vertices. Structure is
    // what makes this read as a fleet under observation rather than a starfield.
    const idx: number[] = [];
    for (let iz = 0; iz < ZS; iz++) {
      for (let ix = 0; ix < XS; ix++) {
        const i = iz * XS + ix;
        if (ix + 1 < XS) idx.push(i, i + 1);
        if (iz + 1 < ZS) idx.push(i, i + XS);
      }
    }
    const geoLines = new THREE.BufferGeometry();
    geoLines.setAttribute("position", aPos);
    geoLines.setAttribute("aRank", aRank);
    geoLines.setAttribute("aPhase", aPhase);
    geoLines.setIndex(idx);

    const uniforms = {
      uTime: { value: 0 },
      uLit: { value: litFraction },
      uScroll: { value: 0 },
      uCalm: { value: 1 },
      uDpr: { value: renderer.getPixelRatio() },
      uDim: { value: new THREE.Color(0x6f68d8) },
      uAccent: { value: new THREE.Color(0x433bff) },
    };

    const mat = new THREE.ShaderMaterial({
      uniforms,
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
      vertexShader: /* glsl */ `
        uniform float uTime, uLit, uScroll, uDpr;
        attribute float aRank, aPhase;
        varying float vLit, vFade, vPulse;
        void main() {
          vec3 p = position;
          // Two slow, non-commensurate swells: the plane breathes rather than
          // ticking, so nothing on screen ever looks like a loading bar.
          p.y += sin(p.x * 0.055 + uTime * 0.21) * 2.6
               + cos(p.z * 0.041 - uTime * 0.16) * 3.4
               + sin((p.x + p.z) * 0.021 + uTime * 0.09) * 1.8;
          p.z += uScroll * 26.0;
          p.z = mod(p.z - 30.0, ${(ZS * STEP).toFixed(1)}) + 30.0 - ${(ZS * STEP).toFixed(1)};

          vLit = step(aRank, uLit);
          vPulse = 0.5 + 0.5 * sin(uTime * 0.7 + aPhase * 6.2831);

          vec4 mv = modelViewMatrix * vec4(p, 1.0);
          float d = -mv.z;
          vFade = smoothstep(240.0, 55.0, d) * smoothstep(6.0, 22.0, d);
          gl_Position = projectionMatrix * mv;
          gl_PointSize = (2.1 + vPulse * 1.5) * uDpr * (66.0 / max(d, 1.0));
        }
      `,
      fragmentShader: /* glsl */ `
        uniform vec3 uDim, uAccent;
        uniform float uCalm;
        varying float vLit, vFade, vPulse;
        void main() {
        #ifdef LATTICE
          // The grid: barely there, but it is what gives the plane its shape.
          gl_FragColor = vec4(uDim, vFade * 0.34 * uCalm);
        #else
          // Only the holdout is drawn as a node. Everything else is lattice.
          if (vLit < 0.5) discard;
          vec2 d = gl_PointCoord - 0.5;
          float r2 = dot(d, d);
          if (r2 > 0.25) discard;
          float a = smoothstep(0.25, 0.0, r2);
          gl_FragColor = vec4(uAccent, a * vFade * (0.62 + vPulse * 0.34) * uCalm);
        #endif
        }
      `,
    });

    const lineMat = mat.clone();
    lineMat.uniforms = uniforms; // one clock, one scroll, one palette
    lineMat.defines = { LATTICE: "" };

    const lattice = new THREE.LineSegments(geoLines, lineMat);
    const points = new THREE.Points(geo, mat);
    scene.add(lattice, points);

    // ── loop ─────────────────────────────────────────────────────────────
    const clock = new THREE.Clock();
    let raf = 0;
    let running = true;

    const resize = () => {
      const w = el.clientWidth || window.innerWidth;
      const h = el.clientHeight || window.innerHeight;
      renderer.setSize(w, h, false);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      uniforms.uDpr.value = renderer.getPixelRatio();
    };
    resize();

    const tick = () => {
      raf = requestAnimationFrame(tick);
      if (!running) return;
      uniforms.uTime.value = clock.getElapsedTime();
      uniforms.uLit.value = lit.current;
      // Scroll slides the fleet past the camera; the plane wraps, so the
      // page can be any length without running out of field.
      const max = document.documentElement.scrollHeight - window.innerHeight;
      uniforms.uScroll.value = max > 0 ? window.scrollY / max : 0;
      // The field is the opening statement; past the first screen it recedes
      // so the evidence sections sit on a calm ground.
      uniforms.uCalm.value =
        1 - Math.min(window.scrollY / (window.innerHeight * 1.15), 1) * 0.72;
      camera.position.y = 27 - uniforms.uScroll.value * 7.0;
      camera.lookAt(0, 0, -48);
      renderer.render(scene, camera);
    };
    raf = requestAnimationFrame(tick);

    const onVisibility = () => {
      running = !document.hidden;
      if (running) clock.getDelta(); // don't jump after a long hide
    };
    document.addEventListener("visibilitychange", onVisibility);

    const ro = new ResizeObserver(resize);
    ro.observe(el);
    window.addEventListener("resize", resize);

    return () => {
      cancelAnimationFrame(raf);
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("resize", resize);
      ro.disconnect();
      geo.dispose();
      geoLines.dispose();
      mat.dispose();
      lineMat.dispose();
      renderer.dispose();
      renderer.domElement.remove();
    };
  }, []);

  return <div className="rl-field" ref={host} aria-hidden="true" />;
}
