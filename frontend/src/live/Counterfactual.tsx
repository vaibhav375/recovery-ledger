import { useEffect, useState } from "react";
import { getLevers, runCounterfactual, type Counterfactual as CF, type Lever, type Trace } from "./api";
import { CitationCard } from "./Range";
import { describeEntry, entryTone } from "../entries";
import { money, titleise } from "../format";

/** Same case, run twice, one fact of the world changed.
 *
 * Every explanation of an autonomous decision is a counterfactual claim: it
 * did X *because* of Y. Usually that claim is written by hand into a
 * rationale string and nobody checks it. Here you change Y and watch. The
 * agent, the kernel, the fitted models and the simulator seed are identical
 * across the two runs — common random numbers, the same discipline the batch
 * experiment uses to compare policies — so any divergence belongs to the
 * lever and nothing else. */
export default function Counterfactual() {
  const [levers, setLevers] = useState<Lever[]>([]);
  const [lever, setLever] = useState<string>("");
  const [result, setResult] = useState<CF | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    getLevers()
      .then((d) => { setLevers(d.levers); setLever(d.levers[0]?.key ?? ""); })
      .catch(() => undefined);
  }, []);

  const run = async (key: string) => {
    setLever(key);
    setBusy(true);
    setResult(null);
    try {
      setResult(await runCounterfactual(key, 0, "auto"));
    } finally {
      setBusy(false);
    }
  };

  const active = levers.find((l) => l.key === lever);

  return (
    <div className="rl-cf">
      <div className="rl-cf-levers">
        {levers.map((l) => (
          <button
            key={l.key}
            type="button"
            aria-pressed={l.key === lever}
            onClick={() => run(l.key)}
            disabled={busy}
          >
            {l.label}
          </button>
        ))}
      </div>

      {active && (
        <p className="rl-cf-expect">
          <span className="rl-dim">Prediction: </span>
          {active.expects}
        </p>
      )}

      {busy && <p className="rl-empty-note">Running the case twice…</p>}

      {result?.error && <p className="rl-note is-error">{result.error}</p>}

      {result && !result.error && (
        <>
          <div className="rl-cf-case">
            <code>{result.case.case_id}</code>
            <span>{result.case.loss_type.replace(/Case$/, "")}</span>
            <span>{money(result.case.amount)}</span>
            <span>{result.case.language}</span>
            {result.case.is_b2b && <span>B2B</span>}
            {result.case.auto_picked && (
              <span className="rl-dim">
                picked automatically — the first case in the roster this lever can act on
              </span>
            )}
          </div>

          <div className={`rl-cf-verdict ${result.diverged ? "is-diverged" : "is-same"}`}>
            {result.diverged
              ? "The decision changed."
              : "The decision did not change."}
          </div>

          {result.note && <p className="rl-note">{result.note}</p>}

          <div className="rl-cf-split">
            <TracePane title="As it happened" trace={result.baseline} />
            <TracePane title={result.lever.label} trace={result.changed} highlight />
          </div>

          {result.changed.denials.length > 0 && (
            <>
              <div className="rl-live-head" style={{ marginTop: 24 }}>
                <span>What refused it</span>
              </div>
              <div className="rl-cited">
                {dedupe(result.changed.denials).map((d) => (
                  <CitationCard key={d.rule} rule={d.rule} citation={d.citation} />
                ))}
              </div>
            </>
          )}
        </>
      )}
    </div>
  );
}

function dedupe<T extends { rule: string }>(items: T[]): T[] {
  const seen = new Set<string>();
  return items.filter((i) => (seen.has(i.rule) ? false : (seen.add(i.rule), true)));
}

function TracePane({
  title, trace, highlight,
}: { title: string; trace: Trace; highlight?: boolean }) {
  return (
    <div className={`rl-cf-pane ${highlight ? "is-highlight" : ""}`}>
      <div className="rl-live-head">
        <span>{title}</span>
        <span className="rl-live-head-meta">{trace.entries.length} entries</span>
      </div>
      <div className="rl-cf-outcome">
        {trace.status === "paused" ? "Paused" : "Ended"} ·{" "}
        <b>{trace.reason ? titleise(trace.reason) : "—"}</b>
        {trace.paid && <span className="rl-chip is-ok">paid</span>}
      </div>
      <ul className="rl-trace rl-trace--compact">
        {trace.entries.map((e) => (
          <li key={e.seq} className={`rl-trace-row is-${entryTone(e)}`}>
            <span className="rl-trace-seq">#{e.seq}</span>
            <span className="rl-trace-type">{e.entry_type}</span>
            <span className="rl-trace-detail">{describeEntry(e)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
