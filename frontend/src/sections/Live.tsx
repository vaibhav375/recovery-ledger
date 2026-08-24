import { useEffect, useState } from "react";
import { motion } from "motion/react";
import InView from "../motion/InView";
import { probe, type Health } from "../live/api";
import Console from "../live/Console";
import Range from "../live/Range";
import Counterfactual from "../live/Counterfactual";
import Chain from "../live/Chain";
import type { Dashboard } from "../types";

type Tab = "console" | "range" | "counterfactual" | "chain";

const TABS: { id: Tab; label: string; blurb: string }[] = [
  { id: "console", label: "Run it", blurb: "Start the agent and watch the loop write its own audit trail." },
  { id: "range", label: "Attack it", blurb: "Fire the red-team suite at the compliance kernel, one attack at a time." },
  { id: "counterfactual", label: "Change one fact", blurb: "The same case, run twice, with one fact of the world different." },
  { id: "chain", label: "Break the trail", blurb: "Tamper with a ledger entry and watch verification catch it." },
];

/** The part of the page that is not a report.
 *
 * Everything above this section is measurement: numbers produced by runs that
 * already happened. This is the system itself, reachable. It needs a backend
 * (`make live`), and when that backend is absent it says so rather than
 * showing controls that do nothing — the static dashboard is a complete
 * product without it. */
export default function Live({ data }: { data: Dashboard }) {
  const [health, setHealth] = useState<Health | null | "checking">("checking");
  const [tab, setTab] = useState<Tab>("console");

  useEffect(() => {
    probe().then(setHealth);
  }, []);

  const active = TABS.find((t) => t.id === tab)!;

  return (
    <section className="rl-livesection" id="live">
      <div className="rl-livesection-inner">
        <InView>
          <p className="rl-sectionmark">The instrument</p>
          <h2 className="rl-h2">
            Reachable, not just reported.
            <span className="rl-dim">
              {" "}Start the agent, attack the kernel, change one fact of the
              world, break the trail. All of it against the running system.
            </span>
          </h2>
        </InView>

        {health === "checking" && <p className="rl-empty-note">Looking for the agent…</p>}

        {health === null && (
          <div className="rl-offline">
            <h3>The live backend is not running.</h3>
            <p>
              Everything above this line came from runs that already happened
              and needs no server. This section drives the agent in real time,
              which does. Start it with:
            </p>
            <pre className="rl-pre">make live</pre>
            <p className="rl-dim">
              Standard library only — nothing to install beyond what{" "}
              <code>make setup</code> already put in the virtualenv. It serves
              this page too, so the same URL gains the controls.
            </p>
          </div>
        )}

        {health && health !== "checking" && (
          <>
            <div className="rl-tabbar">
              {TABS.map((t) => (
                <button key={t.id} onClick={() => setTab(t.id)} aria-current={tab === t.id}>
                  {tab === t.id && (
                    <motion.span
                      layoutId="rl-live-pill"
                      className="rl-tabbar-pill"
                      transition={{ type: "spring", stiffness: 380, damping: 32 }}
                    />
                  )}
                  <span>{t.label}</span>
                </button>
              ))}
            </div>
            <p className="rl-live-blurb">{active.blurb}</p>

            {tab === "console" && <Console />}
            {tab === "range" && <Range />}
            {tab === "counterfactual" && <Counterfactual />}
            {tab === "chain" && <Chain data={data} />}
          </>
        )}
      </div>
    </section>
  );
}
