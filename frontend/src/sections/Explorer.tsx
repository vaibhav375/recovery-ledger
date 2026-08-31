import { useMemo, useState } from "react";
import { motion } from "motion/react";
import type { CaseCard, Dashboard } from "../types";
import InView from "../motion/InView";
import FleetPage from "../components/FleetPage";
import NegotiationPage from "../components/NegotiationPage";
import ListenerPage from "../components/ListenerPage";

type Tab = "cases" | "fleet" | "negotiation" | "listener";

const PAGE = 25;

const TABS: { id: Tab; label: string }[] = [
  { id: "cases", label: "Cases" },
  { id: "fleet", label: "Fleet health" },
  { id: "negotiation", label: "Negotiation" },
  { id: "listener", label: "Listener" },
];

const inr = (n: number) => "₹" + Math.round(n).toLocaleString("en-IN");

/** The evidence, browsable.
 *
 * Deliberately placed after the argument rather than as the landing surface:
 * the numbers only mean something once you have been through the subtraction,
 * so the page earns the right to show a table. */
export default function Explorer({
  data, onSelect,
}: { data: Dashboard; onSelect: (c: CaseCard) => void }) {
  const [tab, setTab] = useState<Tab>("cases");
  const [q, setQ] = useState("");
  const [outcome, setOutcome] = useState("all");
  // The roster runs to hundreds of rows. Showing them all buries the
  // filters and makes the section a wall; a page at a time keeps the
  // register readable and still reaches every case.
  const [shown, setShown] = useState(PAGE);

  const outcomes = useMemo(
    () => ["all", ...Array.from(new Set(data.cases.map((c) => c.outcome)))],
    [data.cases],
  );
  const rows = useMemo(() => {
    const n = q.trim().toLowerCase();
    return data.cases.filter(
      (c) =>
        (outcome === "all" || c.outcome === outcome) &&
        (!n || c.case_id.includes(n) || c.loss_type.includes(n) || c.outcome.includes(n)),
    );
  }, [data.cases, q, outcome]);

  const visible = rows.slice(0, shown);
  const remaining = rows.length - visible.length;

  return (
    <section className="rl-explorer" id="evidence">
      <div className="rl-explorer-inner">
        <p className="rl-sectionmark">The evidence</p>
        <InView>
          <h2 className="rl-h2">
            Every decision, with its provenance.
            <span className="rl-dim"> The ledger is hash-chained; each entry commits to the one before it.</span>
          </h2>
        </InView>

        <div className="rl-tabbar">
          {TABS.map((t) => (
            <button key={t.id} onClick={() => setTab(t.id)} aria-current={tab === t.id}>
              {tab === t.id && (
                <motion.span layoutId="rl-explorer-pill" className="rl-tabbar-pill"
                  transition={{ type: "spring", stiffness: 380, damping: 32 }} />
              )}
              <span>{t.label}</span>
            </button>
          ))}
        </div>

        {tab === "cases" && (
          <>
            <div className="rl-explorer-controls">
              <input
                type="search" value={q} placeholder="Search case, loss type, outcome"
                onChange={(e) => { setQ(e.target.value); setShown(PAGE); }}
              />
              <div className="rl-outcomes">
                {outcomes.map((o) => (
                  <button key={o} aria-pressed={outcome === o} onClick={() => { setOutcome(o); setShown(PAGE); }}>
                    {o.replace(/_/g, " ")}
                  </button>
                ))}
              </div>
            </div>

            <div className="rl-ledger">
              {visible.map((c, i) => (
                <InView key={c.case_id} index={Math.min(i, 12)}>
                  <button className="rl-ledger-row" onClick={() => onSelect(c)}>
                    <code className="rl-ledger-id">{c.case_id}</code>
                    <span className="rl-ledger-type">{c.loss_type.replace(/_/g, " ")}</span>
                    <span className="rl-ledger-lang">{c.language}{c.is_b2b ? " · B2B" : ""}</span>
                    <span className="rl-ledger-amt">{inr(c.amount)}</span>
                    <span className={`rl-ledger-out${c.denied ? " has-deny" : ""}`}>
                      {c.outcome.replace(/_/g, " ")}
                      {c.denied > 0 && <em> · {c.denied} refused</em>}
                    </span>
                  </button>
                </InView>
              ))}
              {!rows.length && <p className="rl-empty-note">No cases match that filter.</p>}
              {remaining > 0 && (
                <div className="rl-ledger-more">
                  <button
                    className="rl-morebtn"
                    onClick={() => setShown((n) => n + PAGE)}
                  >
                    View {Math.min(PAGE, remaining)} more
                  </button>
                  <span>
                    Showing {visible.length} of {rows.length}
                  </span>
                </div>
              )}
            </div>
          </>
        )}

        {tab === "fleet" && <FleetPage data={data} />}
        {tab === "negotiation" && <NegotiationPage data={data} />}
        {tab === "listener" && <ListenerPage data={data} />}
      </div>
    </section>
  );
}
