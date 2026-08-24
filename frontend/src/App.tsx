import { useEffect, useMemo, useState } from "react";
import { loadDashboard } from "./data";
import type { CaseCard, Dashboard } from "./types";
import {
  applyAppearance,
  nextThemePalette,
  readStoredPalette,
  readStoredTheme,
  DARK_PALETTE_STORAGE_KEY,
  LIGHT_PALETTE_STORAGE_KEY,
  THEME_STORAGE_KEY,
  type ThemeMode,
  type ThemePalette,
} from "./vendor/theme";

import Sidebar from "./components/Sidebar";
import Topbar from "./components/Topbar";
import OverviewPage from "./components/OverviewPage";
import CasesPage from "./components/CasesPage";
import CaseDetail from "./components/CaseDetail";
import CompliancePage from "./components/CompliancePage";
import FleetPage from "./components/FleetPage";
import NegotiationPage from "./components/NegotiationPage";
import ListenerPage from "./components/ListenerPage";

export type ViewId =
  | "overview"
  | "cases"
  | "compliance"
  | "fleet"
  | "negotiation"
  | "listener";

export const VIEWS: { id: ViewId; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "cases", label: "Cases" },
  { id: "compliance", label: "Compliance kernel" },
  { id: "fleet", label: "Fleet health" },
  { id: "negotiation", label: "Negotiation" },
  { id: "listener", label: "Listener" },
];

export default function App() {
  const [data, setData] = useState<Dashboard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [view, setView] = useState<ViewId>("overview");
  const [selected, setSelected] = useState<CaseCard | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);

  // Theme state uses ThreeUI's own module: light/dark/system plus five
  // palettes, persisted to localStorage under its keys.
  const [mode, setMode] = useState<ThemeMode>(() => readStoredTheme());
  const [lightPalette, setLightPalette] = useState<ThemePalette>(() =>
    readStoredPalette(LIGHT_PALETTE_STORAGE_KEY),
  );
  const [darkPalette, setDarkPalette] = useState<ThemePalette>(() =>
    readStoredPalette(DARK_PALETTE_STORAGE_KEY),
  );

  useEffect(() => {
    applyAppearance(mode, lightPalette, darkPalette);
    try {
      localStorage.setItem(THEME_STORAGE_KEY, mode);
      localStorage.setItem(LIGHT_PALETTE_STORAGE_KEY, lightPalette);
      localStorage.setItem(DARK_PALETTE_STORAGE_KEY, darkPalette);
    } catch {
      /* private browsing — appearance still applies for this session */
    }
  }, [mode, lightPalette, darkPalette]);

  useEffect(() => {
    loadDashboard().then(setData).catch((e) => setError(String(e)));
  }, []);

  const scheme = mode === "system" ? "light" : mode;
  const cyclePalette = () => {
    if (scheme === "dark") setDarkPalette(nextThemePalette(darkPalette));
    else setLightPalette(nextThemePalette(lightPalette));
  };

  const body = useMemo(() => {
    if (error) {
      return (
        <div className="rl-empty">
          <h1>Could not load the audit trail</h1>
          <p className="lede">{error}</p>
          <p className="lede">
            Generate it with <code>make dashboard</code>, which writes{" "}
            <code>dashboard/dist/data.json</code>.
          </p>
        </div>
      );
    }
    if (!data) return <div className="rl-empty"><p className="lede">Loading…</p></div>;

    switch (view) {
      case "cases":
        return <CasesPage data={data} onSelect={setSelected} />;
      case "compliance":
        return <CompliancePage data={data} />;
      case "fleet":
        return <FleetPage data={data} />;
      case "negotiation":
        return <NegotiationPage data={data} />;
      case "listener":
        return <ListenerPage data={data} />;
      default:
        return <OverviewPage data={data} />;
    }
  }, [data, error, view]);

  return (
    <>
      <Topbar
        mode={mode}
        onCycleMode={() =>
          setMode(mode === "dark" ? "light" : mode === "light" ? "system" : "dark")
        }
        onCyclePalette={cyclePalette}
        onOpenNav={() => setSidebarOpen(true)}
        source={data?.source ?? ""}
      />
      <div className="app">
        <Sidebar
          view={view}
          onSelect={(v) => {
            setView(v);
            setSidebarOpen(false);
          }}
          open={sidebarOpen}
          data={data}
        />
        {sidebarOpen && (
          <button
            className="mobile-nav-scrim"
            aria-label="Close navigation"
            onClick={() => setSidebarOpen(false)}
          />
        )}
        <div className="pane">
          <div className="pane-scroll scroll-area">{body}</div>
        </div>
      </div>
      {selected && <CaseDetail c={selected} onClose={() => setSelected(null)} />}
    </>
  );
}
