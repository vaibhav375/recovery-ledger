import type { ThemeMode } from "../vendor/theme";

export default function Topbar({
  mode, onCycleMode, onCyclePalette, onOpenNav, source,
}: {
  mode: ThemeMode;
  onCycleMode: () => void;
  onCyclePalette: () => void;
  onOpenNav: () => void;
  source: string;
}) {
  return (
    <header className="topbar">
      <button className="icon-btn rl-nav-toggle" aria-label="Open navigation" onClick={onOpenNav}>
        ☰
      </button>
      <div className="rl-brand">
        <strong>Recovery Ledger</strong>
        <span className="rl-brand-sub">audit trail</span>
      </div>
      <div className="topbar-actions rl-topbar-actions">
        <span className="rl-source" title={source}>{source}</span>
        <button className="rl-chip-btn" onClick={onCyclePalette} title="Cycle palette">
          palette
        </button>
        <button className="rl-chip-btn" onClick={onCycleMode} title="Cycle light / dark / system">
          {mode}
        </button>
      </div>
    </header>
  );
}
