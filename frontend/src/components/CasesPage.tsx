import { useMemo, useState } from "react";
import type { CaseCard, Dashboard } from "../types";
import { money } from "../format";

export default function CasesPage({
  data, onSelect,
}: { data: Dashboard; onSelect: (c: CaseCard) => void }) {
  const [q, setQ] = useState("");
  const [outcome, setOutcome] = useState("all");

  const outcomes = useMemo(
    () => ["all", ...Array.from(new Set(data.cases.map((c) => c.outcome)))],
    [data.cases],
  );

  const rows = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return data.cases.filter(
      (c) =>
        (outcome === "all" || c.outcome === outcome) &&
        (!needle ||
          c.case_id.toLowerCase().includes(needle) ||
          c.loss_type.toLowerCase().includes(needle) ||
          c.outcome.toLowerCase().includes(needle)),
    );
  }, [data.cases, q, outcome]);

  return (
    <main className="browse-page rl-page">
      <header className="browse-header">
        <div className="browse-heading-row">
          <h1>Cases</h1>
          <p className="lede">
            {rows.length} of {data.cases.length} — select a case for its full decision trace
          </p>
        </div>
        <div className="browse-controls-row rl-controls">
          <label className="browse-filter rl-filter">
            <input
              type="search"
              value={q}
              placeholder="Search case id, loss type, outcome…"
              onChange={(e) => setQ(e.target.value)}
            />
          </label>
          <div className="browse-category-filters rl-filters">
            {outcomes.map((o) => (
              <button
                key={o}
                aria-pressed={outcome === o}
                onClick={() => setOutcome(o)}
              >
                {o}
              </button>
            ))}
          </div>
        </div>
      </header>

      <div className="browse-grid rl-cases">
        {rows.map((c) => (
          <article key={c.case_id} className="browse-item rl-case">
            <button className="rl-case-btn" onClick={() => onSelect(c)}>
              <div className="rl-case-id">{c.case_id}</div>
              <div className="rl-case-meta">
                {c.loss_type} · {c.language} · {c.channel}
                {c.is_b2b ? " · B2B" : ""}
              </div>
              <div className="rl-case-amt">{money(c.amount)}</div>
              <div className="rl-case-chips">
                <span className="rl-chip">{c.outcome}</span>
                {c.denied > 0 ? (
                  <span className="rl-chip is-deny">{c.denied} denied</span>
                ) : (
                  <span className="rl-chip is-ok">{c.certificates} certs</span>
                )}
              </div>
            </button>
          </article>
        ))}
      </div>
    </main>
  );
}
