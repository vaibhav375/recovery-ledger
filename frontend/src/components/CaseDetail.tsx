import { useState } from "react";
import type { CaseCard } from "../types";
import { money } from "../format";
import { describeEntry, shortHash } from "../entries";

type Tab = "timeline" | "certificates" | "raw";

export default function CaseDetail({ c, onClose }: { c: CaseCard; onClose: () => void }) {
  const [tab, setTab] = useState<Tab>("timeline");
  const certs = c.timeline.filter((t) => t.type === "certificate");

  return (
    <div className="rl-drawer" role="dialog" aria-label={`Case ${c.case_id}`}>
      <button className="rl-drawer-scrim" aria-label="Close" onClick={onClose} />
      <div className="rl-drawer-panel">
        <header className="rl-drawer-head">
          <div>
            <h1>{c.case_id}</h1>
            <p className="lede">
              {c.loss_type} · {money(c.amount)} · outcome: {c.outcome}
            </p>
          </div>
          <button className="icon-btn" aria-label="Close" onClick={onClose}>✕</button>
        </header>

        <div className="rl-tabs">
          {(["timeline", "certificates", "raw"] as Tab[]).map((t) => (
            <button key={t} aria-selected={tab === t} onClick={() => setTab(t)}>{t}</button>
          ))}
        </div>

        {tab === "timeline" && (
          <ol className="rl-timeline">
            {c.timeline.map((s) => {
              const decision = s.type === "certificate" ? s.payload.decision : null;
              const tone = decision === "DENY" ? "deny" : decision === "ALLOW" ? "allow" : "";
              return (
                <li key={s.seq} className={`rl-step ${tone}`}>
                  <div className="rl-step-title">
                    {s.type}{decision ? ` — ${decision}` : ""}
                  </div>
                  <div className="rl-step-detail">{describeEntry(s)}</div>
                  <div className="rl-step-hash">
                    #{s.seq} {shortHash(s.prev)}&nbsp;→&nbsp;{shortHash(s.hash)}
                  </div>
                </li>
              );
            })}
          </ol>
        )}

        {tab === "certificates" && (
          certs.length ? certs.map((t) => (
            <section key={t.seq} className="rl-cert">
              <h2>
                {t.payload.action_type} —{" "}
                <span className={t.payload.decision === "DENY" ? "rl-fail" : "rl-pass"}>
                  {t.payload.decision}
                </span>
              </h2>
              {(t.payload.rule_results ?? []).map((r: any) => (
                <div key={r.rule_name} className="rl-rule">
                  <code>{r.rule_name}</code>
                  <span className={r.passed ? "rl-pass" : "rl-fail"}>
                    {r.passed ? "pass" : "DENY"}
                  </span>
                </div>
              ))}
            </section>
          )) : <p className="lede">No certificates for this case.</p>
        )}

        {tab === "raw" && (
          <pre className="rl-pre">{JSON.stringify(c.timeline, null, 2)}</pre>
        )}
      </div>
    </div>
  );
}
