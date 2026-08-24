import { VIEWS, type ViewId } from "../App";
import type { Dashboard } from "../types";
import AnimatedTabs from "../motion/AnimatedTabs";

export default function Sidebar({
  view, onSelect, open, data,
}: {
  view: ViewId;
  onSelect: (v: ViewId) => void;
  open: boolean;
  data: Dashboard | null;
}) {
  // A view whose experiment has not been run says so, rather than rendering an
  // empty page that looks broken.
  const available: Record<ViewId, boolean> = {
    overview: true,
    cases: true,
    compliance: true,
    fleet: Boolean(data?.fleet),
    negotiation: Boolean(data?.negotiation),
    listener: Boolean(data?.listener),
  };

  return (
    <nav className={`sidebar rl-sidebar${open ? " is-open" : ""}`} aria-label="Sections">
      <AnimatedTabs
        layoutId="rl-nav-pill"
        className="rl-nav"
        itemClassName="rl-nav-item"
        value={view}
        onChange={onSelect}
        items={VIEWS.map((v) => ({
          id: v.id,
          label: v.label,
          flag: available[v.id] ? undefined : "not run",
        }))}
      />
      <div className="rl-sidebar-foot">
        <p>Every outbound action is gated by a deterministic compliance kernel. No certificate, no action.</p>
      </div>
    </nav>
  );
}
