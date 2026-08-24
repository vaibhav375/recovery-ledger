import { VIEWS, type ViewId } from "../App";
import type { Dashboard } from "../types";

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
  const availability: Record<ViewId, boolean> = {
    overview: true,
    cases: true,
    compliance: true,
    fleet: Boolean(data?.fleet),
    negotiation: Boolean(data?.negotiation),
    listener: Boolean(data?.listener),
  };

  return (
    <nav className={`sidebar rl-sidebar${open ? " is-open" : ""}`} aria-label="Sections">
      <ul className="rl-nav">
        {VIEWS.map((v) => (
          <li key={v.id}>
            <button
              className="rl-nav-item"
              aria-current={view === v.id}
              onClick={() => onSelect(v.id)}
            >
              <span>{v.label}</span>
              {!availability[v.id] && <span className="rl-nav-flag">not run</span>}
            </button>
          </li>
        ))}
      </ul>
      <div className="rl-sidebar-foot">
        <p>
          Every outbound action is gated by a deterministic compliance kernel.
          No certificate, no action.
        </p>
      </div>
    </nav>
  );
}
