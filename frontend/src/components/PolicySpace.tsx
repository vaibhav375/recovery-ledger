import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";

/** The decision space, as a space you can walk around.
 *
 * WHY THIS IS 3D, WHICH IS A CLAIM THAT NEEDS DEFENDING
 *
 * Three dimensions are usually worse than two for reading data: perspective
 * distorts distance, and points hide behind other points. A 3D chart has to
 * earn the third axis by carrying information the flat version cannot, and it
 * has to make occlusion recoverable. Both conditions hold here and neither is
 * incidental.
 *
 * The agent contacts on expected value, and expected value is predicted uplift
 * TIMES rupees at risk. The decision therefore depends on two inputs at once,
 * and the boundary between "contact" and "wait" is a *surface* over them — a
 * hyperbola-like sheet where tau_hat x amount meets the cost of the message.
 * The flat quadrant chart elsewhere on this page had to drop `amount`
 * entirely, which is why it cannot answer the obvious question about its own
 * bottom-left corner: why did the agent contact that case when predicted
 * uplift was almost nothing? Because it was a large invoice. That fact only
 * exists on an axis the 2D chart does not have.
 *
 * The vertical axis is truth. A point's height is what contact was really
 * worth for that customer, which the model never sees. So the picture is:
 * where the agent decided to act, over the two things it decided on, against
 * the thing it was trying to predict.
 *
 * And occlusion is recoverable because you can drag it. That is the whole
 * argument for interactivity here — not that rotation is pleasant, but that a
 * static 3D projection would be strictly worse than a flat chart and an
 * orbitable one is not.
 *
 * WHAT TO LOOK FOR
 *
 * Contacted points sit high and to the right: the agent is spending its
 * messages where predicted uplift and amount are both large. Below the grey
 * plane is where contact destroys value. Contacted points down there are the
 * agent's real mistakes, and there are fewer than the model's 0.36 correlation
 * with truth would lead you to expect — because the churn term has to agree
 * before a contact happens, so two models must both be wrong.
 */

export type ScatterPoint = {
  tau_hat: number;
  tau_true: number;
  amount: number;
  contacted: number;
  loss_type?: string;
};

const ACCENT = 0x433bff;
const MUTED = 0x6b6795;

export default function PolicySpace({ points }: { points: ScatterPoint[] }) {
  const host = useRef<HTMLDivElement>(null);
  const [dragged, setDragged] = useState(false);

  useEffect(() => {
    const el = host.current;
    if (!el || !points?.length) return;

    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    } catch {
      return; // guarded upstream; a chart must never break the page
    }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setClearColor(0x000000, 0);
    el.appendChild(renderer.domElement);

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(42, 1, 0.1, 100);
    camera.position.set(9, 6.5, 11);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.enablePan = false;
    controls.minDistance = 7;
    controls.maxDistance = 24;
    // Stop short of the poles: looking straight down collapses the vertical
    // axis, which is the one carrying the truth.
    controls.maxPolarAngle = Math.PI * 0.86;
    controls.minPolarAngle = Math.PI * 0.12;
    controls.addEventListener("start", () => setDragged(true));

    // ── scales ───────────────────────────────────────────────────────
    // Robust domains, as in the flat charts: a few extreme predictions would
    // otherwise compress everything else into a sliver.
    const q = (arr: number[], f: number) => {
      const a = [...arr].sort((m, n) => m - n);
      return a[Math.round(f * (a.length - 1))];
    };
    const amounts = points.map((p) => Math.log10(Math.max(p.amount, 1)));
    const taus = points.map((p) => p.tau_hat);
    const trues = points.map((p) => p.tau_true);
    const S = 5; // half-extent of the cube
    const scale = (v: number, lo: number, hi: number) =>
      ((Math.min(Math.max(v, lo), hi) - lo) / (hi - lo) - 0.5) * 2 * S;
    const [aLo, aHi] = [q(amounts, 0.01), q(amounts, 0.99)];
    const [tLo, tHi] = [q(taus, 0.01), q(taus, 0.99)];
    const [rLo, rHi] = [q(trues, 0.01), q(trues, 0.99)];

    // ── the plane where contact starts costing money ─────────────────
    const zeroY = scale(0, rLo, rHi);
    const plane = new THREE.Mesh(
      new THREE.PlaneGeometry(S * 2, S * 2),
      new THREE.MeshBasicMaterial({
        color: 0xff6b7f, transparent: true, opacity: 0.055,
        side: THREE.DoubleSide, depthWrite: false,
      }),
    );
    plane.rotation.x = -Math.PI / 2;
    plane.position.y = zeroY;
    scene.add(plane);

    const planeEdge = new THREE.LineSegments(
      new THREE.EdgesGeometry(new THREE.PlaneGeometry(S * 2, S * 2)),
      new THREE.LineBasicMaterial({ color: 0xff6b7f, transparent: true, opacity: 0.3 }),
    );
    planeEdge.rotation.x = -Math.PI / 2;
    planeEdge.position.y = zeroY;
    scene.add(planeEdge);

    // ── the cube, so rotation has a frame of reference ───────────────
    const box = new THREE.LineSegments(
      new THREE.EdgesGeometry(new THREE.BoxGeometry(S * 2, S * 2, S * 2)),
      new THREE.LineBasicMaterial({ color: 0xdedcff, transparent: true, opacity: 0.1 }),
    );
    scene.add(box);

    // ── the cases ────────────────────────────────────────────────────
    const build = (subset: ScatterPoint[], color: number, size: number, opacity: number) => {
      if (!subset.length) return null;
      const pos = new Float32Array(subset.length * 3);
      subset.forEach((p, i) => {
        pos[i * 3] = scale(Math.log10(Math.max(p.amount, 1)), aLo, aHi);
        pos[i * 3 + 1] = scale(p.tau_true, rLo, rHi);
        pos[i * 3 + 2] = scale(p.tau_hat, tLo, tHi);
      });
      const g = new THREE.BufferGeometry();
      g.setAttribute("position", new THREE.BufferAttribute(pos, 3));
      const m = new THREE.PointsMaterial({
        color, size, sizeAttenuation: true, transparent: true, opacity,
        depthWrite: false,
      });
      const pts = new THREE.Points(g, m);
      scene.add(pts);
      return { g, m, pts };
    };

    const left = build(points.filter((p) => !p.contacted), MUTED, 0.09, 0.45);
    const hit = build(points.filter((p) => p.contacted), ACCENT, 0.15, 0.95);

    // ── loop ─────────────────────────────────────────────────────────
    const resize = () => {
      const w = el.clientWidth || 600;
      const h = el.clientHeight || 420;
      renderer.setSize(w, h, false);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
    };
    resize();

    let raf = 0;
    let running = true;
    let idle = 0;
    const tick = () => {
      raf = requestAnimationFrame(tick);
      if (!running) return;
      // A slow drift until the first drag, so it reads as manipulable without
      // a label telling you so. Stops the moment you take hold of it.
      if (!controls.enabled) return;
      idle += 1;
      if (!dragged && idle < 100000) {
        const t = idle * 0.0016;
        camera.position.x = Math.sin(t) * 13;
        camera.position.z = Math.cos(t) * 13;
        camera.position.y = 6.5;
        camera.lookAt(0, 0, 0);
      }
      controls.update();
      renderer.render(scene, camera);
    };
    raf = requestAnimationFrame(tick);

    const onVis = () => { running = !document.hidden; };
    document.addEventListener("visibilitychange", onVis);
    const ro = new ResizeObserver(resize);
    ro.observe(el);

    return () => {
      cancelAnimationFrame(raf);
      document.removeEventListener("visibilitychange", onVis);
      ro.disconnect();
      controls.dispose();
      [left, hit].forEach((o) => { o?.g.dispose(); o?.m.dispose(); });
      plane.geometry.dispose();
      (plane.material as THREE.Material).dispose();
      renderer.dispose();
      renderer.domElement.remove();
    };
  }, [points, dragged]);

  return (
    <div className="rl-space">
      <div className="rl-space-canvas" ref={host} />
      <div className="rl-space-legend">
        <span className="rl-space-key is-hit">contacted</span>
        <span className="rl-space-key">left alone</span>
        <span className="rl-space-key is-plane">below here, contact destroys value</span>
        <span className="rl-space-hint">{dragged ? "drag to rotate · scroll to zoom" : "drag it"}</span>
      </div>
      <div className="rl-space-axes">
        <span>← rupees at risk (log)</span>
        <span>↑ true uplift</span>
        <span>↗ predicted uplift τ̂</span>
      </div>
    </div>
  );
}
