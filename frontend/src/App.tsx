import { useEffect, useMemo, useState } from "react";
import { loadDashboard } from "./data";
import type { CaseCard, Dashboard } from "./types";
import {
  applyAppearance,
  DARK_PALETTE_STORAGE_KEY,
  LIGHT_PALETTE_STORAGE_KEY,
  THEME_STORAGE_KEY,
  type ThemeMode,
  type ThemePalette,
} from "./vendor/theme";

import { useLenis } from "./motion/useLenis";
import Scene from "./components/Scene";
import Opening from "./sections/Opening";
import Subtraction from "./sections/Subtraction";
import Frontier from "./sections/Frontier";
import Silence from "./sections/Silence";
import Kernel from "./sections/Kernel";
import Audit from "./sections/Audit";
import Live from "./sections/Live";
import Explorer from "./sections/Explorer";
import CaseDetail from "./components/CaseDetail";

export default function App() {
  const [data, setData] = useState<Dashboard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<CaseCard | null>(null);

  useLenis(true);

  // Fixed to the dark ground. The palette's #050315 is the page, and the
  // ambient WebGL field only reads correctly against it — a light variant
  // would be a different design, not a toggle.
  useEffect(() => {
    applyAppearance("dark" as ThemeMode, "mono" as ThemePalette, "mono" as ThemePalette);
    try {
      localStorage.setItem(THEME_STORAGE_KEY, "dark");
      localStorage.setItem(LIGHT_PALETTE_STORAGE_KEY, "mono");
      localStorage.setItem(DARK_PALETTE_STORAGE_KEY, "mono");
    } catch {
      /* private browsing */
    }
  }, []);

  useEffect(() => {
    loadDashboard().then(setData).catch((e) => setError(String(e)));
  }, []);

  const figures = useMemo(() => {
    if (!data) return null;
    const b = data.batch;
    const dnd = data.summary.stop_reasons?.do_not_disturb ?? 0;
    const promises = data.cases.reduce(
      (n, c) => n + c.timeline.filter((t) => t.type === "pause").length,
      0,
    );
    return {
      gross: b?.gross_treatment_recovered ?? 0,
      holdout: b?.gross_holdout_recovered ?? 0,
      holdoutRate: b?.holdout_recovery_rate ?? 0,
      incremental: b?.incremental_per_1000_cases?.point ?? 0,
      ciLow: b?.incremental_per_1000_cases?.ci_low ?? 0,
      ciHigh: b?.incremental_per_1000_cases?.ci_high ?? 0,
      contacts: b?.contacts_sent ?? 0,
      dnd,
      promises,
      futile: data.fleet?.futile_retries_avoided ?? 0,
    };
  }, [data]);

  if (error) {
    return (
      <main className="rl-boot">
        <h1>No audit trail found</h1>
        <p>
          Generate it with <code>make dashboard</code>, which writes{" "}
          <code>dashboard/dist/data.json</code>.
        </p>
        <p className="rl-boot-err">{error}</p>
      </main>
    );
  }

  if (!data || !figures) {
    return (
      <main className="rl-boot">
        <span className="rl-boot-pulse" />
      </main>
    );
  }

  return (
    <>
      <Scene litFraction={figures.holdoutRate} />

      <header className="rl-topline">
        <span className="rl-wordmark">Recovery Ledger</span>
        <span className="rl-topline-meta">{data.source}</span>
      </header>

      <main>
        <Opening holdoutRate={figures.holdoutRate} />
        <Subtraction
          gross={figures.gross}
          holdout={figures.holdout}
          incrementalPer1000={figures.incremental}
          ciLow={figures.ciLow}
          ciHigh={figures.ciHigh}
          holdoutRate={figures.holdoutRate}
        />
        <Frontier data={data} />
        <Silence
          dndCases={figures.dnd}
          promiseWindows={figures.promises}
          futileRetries={figures.futile}
          contactsSent={figures.contacts}
          totalCases={data.summary.cases}
        />
        <Kernel data={data} />
        <Audit data={data} />
        <Live data={data} />
        <Explorer data={data} onSelect={setSelected} />
      </main>

      <footer className="rl-footer">
        <span>Razorpay AI Buildathon · Track 03</span>
        <span>
          Every number here was produced by code in this repository and is
          reproducible.
        </span>
      </footer>

      {selected && <CaseDetail c={selected} onClose={() => setSelected(null)} />}
    </>
  );
}
