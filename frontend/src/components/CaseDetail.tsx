import { useState } from "react";
import type { CaseCard } from "../types";
import { money } from "../format";

type Tab = "timeline" | "certificates" | "raw";

function describe(step: CaseCard["timeline"][number]): string {
  const p = step.payload ?? {};
  switch (step.type) {
    case "decision": return p.rationale ?? "";
    case "diagnosis": return p.narration ?? "";
    case "stop": return `reason: ${p.reason}`;
    case "pause": return `until ${p.resume_at}`;
    case "reply": return `customer intent: ${p.intent}`;
    case "action_result":
      return `${p.executed ? "executed" : "not executed"} ${p.action_type ?? ""}`;
    case "certificate": {
      const failed = (p.rule_results ?? []).filter((r: any) => !r.passed).map((r: any) => r.rule_name);
      return failed.length ? `denied by ${failed.join(", ")}` : "all rules passed";
    }
    case "case_ingested": return "case opened";
    default: return "";
  }
}

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
                  <div className="rl-step-detail">{describe(s)}</div>
                  <div className="rl-step-hash">
                    #{s.seq} {s.prev}&nbsp;→&nbsp;{s.hash}
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
