import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { motion } from "motion/react";
import {
  killRun,
  startRun,
  streamRun,
  type LiveEvent,
  type RosterCase,
  type RunSummary,
} from "./api";
import { describeEntry, entryTone, shortHash } from "../entries";
import { money, titleise } from "../format";

type LedgerRow = {
  seq: number;
  case_id: string;
  entry_type: string;
  payload: Record<string, any>;
  hash: string;
  t_ms: number;
};

/** Only the tail is rendered. A 400-case run writes ~1,000 entries and React
 *  should not be asked to keep a thousand animated rows alive to show you the
 *  twenty you can actually read. */
const TAIL = 26;

export default function Console() {
  const [runId, setRunId] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [roster, setRoster] = useState<RosterCase[]>([]);
  const [rows, setRows] = useState<LedgerRow[]>([]);
  const [meta, setMeta] = useState<{ correlation: number; policy: string } | null>(null);
  const [summary, setSummary] = useState<RunSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [killed, setKilled] = useState(false);
  const [nCases, setNCases] = useState(60);
  const [paceMs, setPaceMs] = useState(60);

  const closeRef = useRef<(() => void) | null>(null);
  const countsRef = useRef({ entries: 0, certificates: 0, denials: 0, contacts: 0 });
  const [counts, setCounts] = useState(countsRef.current);
  const [worked, setWorked] = useState<Record<string, string>>({});

  useEffect(() => () => closeRef.current?.(), []);

  const onEvent = useCallback((e: LiveEvent) => {
    if (e.type === "run_started") {
      setRoster(e.roster);
      setMeta({ correlation: e.uplift_correlation, policy: e.policy });
      return;
    }
    if (e.type === "run_finished") {
      setRunning(false);
      setSummary(e.summary);
      setError(e.error);
      return;
    }
    if (e.type !== "ledger") return;

    const c = countsRef.current;
    c.entries += 1;
    if (e.entry_type === "certificate") {
      c.certificates += 1;
      if (e.payload?.decision === "DENY") c.denials += 1;
    }
    if (e.entry_type === "action_result") {
      const action = String(e.payload?.action_type ?? "");
      if (/NUDGE|ESCALATE|NEGOTIATE/i.test(action)) c.contacts += 1;
    }
    setCounts({ ...c });

    if (e.entry_type === "stop" || e.entry_type === "pause") {
      const label = e.entry_type === "stop" ? String(e.payload?.reason) : "paused";
      setWorked((w) => ({ ...w, [e.case_id]: label }));
    } else {
      setWorked((w) => (w[e.case_id] ? w : { ...w, [e.case_id]: "working" }));
    }

    setRows((prev) => {
      const next = prev.concat({
        seq: e.seq,
        case_id: e.case_id,
        entry_type: e.entry_type,
        payload: e.payload,
        hash: e.hash,
        t_ms: e.t_ms,
      });
      return next.length > TAIL ? next.slice(next.length - TAIL) : next;
    });
  }, []);

  const begin = async () => {
    closeRef.current?.();
    countsRef.current = { entries: 0, certificates: 0, denials: 0, contacts: 0 };
    setCounts(countsRef.current);
    setRows([]);
    setRoster([]);
    setWorked({});
    setSummary(null);
    setError(null);
    setKilled(false);
    setRunning(true);
    try {
      const { run_id } = await startRun(20260823, nCases, paceMs);
      setRunId(run_id);
      closeRef.current = streamRun(run_id, onEvent, () => setRunning(false));
    } catch (err) {
      setRunning(false);
      setError(String(err));
    }
  };

  const halt = async () => {
    if (!runId) return;
    setKilled(true);
    await killRun(runId);
  };

  const stopReasonRows = useMemo(() => {
    if (!summary) return [];
    return Object.entries(summary.stop_reasons).sort((a, b) => b[1] - a[1]);
  }, [summary]);

  return (
    <div className="rl-live">
      <div className="rl-live-controls">
        <button className="rl-btn rl-btn--primary" onClick={begin} disabled={running}>
          {running ? "Running…" : "Run the agent"}
        </button>
        <button
          className="rl-btn rl-btn--halt"
          onClick={halt}
          disabled={!running || killed}
          title="Engages the same KillSwitch stopping rule 11 checks"
        >
          {killed ? "Kill switch engaged" : "Engage kill switch"}
        </button>

        <label className="rl-control">
          <span>Cases</span>
          <input
            type="range" min={10} max={400} step={10} value={nCases}
            disabled={running}
            onChange={(e) => setNCases(Number(e.target.value))}
          />
          <b>{nCases}</b>
        </label>
        <label className="rl-control">
          <span>Throttle</span>
          <input
            type="range" min={0} max={200} step={10} value={paceMs}
            disabled={running}
            onChange={(e) => setPaceMs(Number(e.target.value))}
          />
          <b>{paceMs} ms</b>
        </label>
      </div>

      <p className="rl-live-caveat">
        The throttle is a deliberate pause between ledger writes so a human can
        read the loop and reach the kill switch. It never touches the reported
        timings — every entry below carries the agent's own elapsed
        milliseconds, and the summary reports agent time and wall-clock time
        separately.
      </p>

      <div className="rl-live-counters">
        <Counter label="Ledger entries" value={counts.entries} />
        <Counter label="Certificates" value={counts.certificates} note="one per attempted action" />
        <Counter label="Refused" value={counts.denials} tone="deny" />
        <Counter label="Messages sent" value={counts.contacts} />
      </div>

      <div className="rl-live-split">
        <div className="rl-live-roster">
          <div className="rl-live-head">
            <span>Fleet</span>
            {meta && (
              <span className="rl-live-head-meta">
                {meta.policy} · corr(τ̂, τ) = {meta.correlation.toFixed(2)}
              </span>
            )}
          </div>
          {roster.length === 0 ? (
            <p className="rl-empty-note">
              Press <b>Run the agent</b>. Cases are generated from a fixed seed,
              so the fleet is the same every time.
            </p>
          ) : (
            <ul className="rl-roster">
              {roster.slice(0, 120).map((c) => {
                const state = worked[c.case_id];
                return (
                  <li key={c.case_id} className={`rl-roster-row is-${state ? statusClass(state) : "idle"}`}>
                    <span className="rl-roster-id">{c.case_id.replace("case_0000", "")}</span>
                    <span className="rl-roster-type">{humanType(c.loss_type)}</span>
                    <span className="rl-roster-tau" title="predicted incremental effect of contacting">
                      τ̂ {c.tau_hat.toFixed(3)}
                    </span>
                    <span className="rl-roster-amt">{money(c.amount)}</span>
                    <span className="rl-roster-state">{state ? titleise(state) : "—"}</span>
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        <div className="rl-live-trace">
          <div className="rl-live-head">
            <span>Ledger, as it is written</span>
            <span className="rl-live-head-meta">last {TAIL}</span>
          </div>
          {rows.length === 0 ? (
            <p className="rl-empty-note">Nothing yet.</p>
          ) : (
            <ul className="rl-trace">
              {rows.map((r) => (
                <motion.li
                  key={r.seq}
                  className={`rl-trace-row is-${entryTone({ entry_type: r.entry_type, payload: r.payload })}`}
                  initial={{ opacity: 0, x: -8 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ duration: 0.24, ease: [0.16, 1, 0.3, 1] }}
                >
                  <span className="rl-trace-seq">#{r.seq}</span>
                  <span className="rl-trace-type">{r.entry_type}</span>
                  <span className="rl-trace-detail">
                    {describeEntry({ entry_type: r.entry_type, payload: r.payload })}
                  </span>
                  <span className="rl-trace-hash">{shortHash(r.hash)}</span>
                  <span className="rl-trace-t">{r.t_ms.toFixed(0)} ms</span>
                </motion.li>
              ))}
            </ul>
          )}
        </div>
      </div>

      {error && <p className="rl-note is-error">The run failed: {error}</p>}

      {summary && (
        <div className="rl-live-summary">
          <div className="rl-grid">
            <Stat label="Cases worked" value={String(summary.cases)} />
            <Stat label="Resolved" value={String(summary.resolved)} />
            <Stat label="Recovered" value={money(summary.recovered_rupees)} />
            <Stat
              label="Agent time"
              value={`${summary.agent_ms.toFixed(0)} ms`}
              note={`${(summary.agent_ms / summary.cases).toFixed(1)} ms per case · wall clock ${(summary.wall_ms / 1000).toFixed(1)}s including throttle`}
            />
          </div>

          <div className="rl-live-reasons">
            {stopReasonRows.map(([reason, n]) => (
              <span key={reason} className={`rl-chip ${reason === "global_kill_switch" ? "is-halt" : ""}`}>
                {titleise(reason)} · {n}
              </span>
            ))}
          </div>

          {summary.killed && (
            <p className="rl-note">
              The kill switch stopped this run.{" "}
              {summary.stop_reasons.global_kill_switch ?? 0} cases terminated with{" "}
              <code>global_kill_switch</code> — written to the ledger, where you
              can read it back. This is stopping rule 11, not a UI that stopped
              drawing.
            </p>
          )}

          <p className={`rl-note ${summary.chain.ok ? "is-alert" : "is-error"}`}>
            <strong>Chain check:</strong> {summary.chain.detail}
          </p>

          {summary.still_open.length > 0 && (
            <p className="rl-note">
              <strong>{summary.still_open.length} still open</strong> at the
              horizon — cases paused on a promise to pay that had not come due.
              Reported, not counted as failures and not dropped.
            </p>
          )}
        </div>
      )}
    </div>
  );
}

function statusClass(state: string): string {
  if (state === "working") return "working";
  if (state === "resolved") return "resolved";
  if (state === "global_kill_switch") return "halted";
  if (state === "paused") return "paused";
  return "stopped";
}

function humanType(t: string): string {
  return t
    .replace(/Case$/, "")
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .toLowerCase();
}

function Counter({
  label, value, note, tone,
}: { label: string; value: number; note?: string; tone?: "deny" }) {
  return (
    <div className="rl-counter">
      <span className={`rl-counter-value ${tone === "deny" ? "is-deny" : ""}`}>
        {value.toLocaleString("en-IN")}
      </span>
      <span className="rl-counter-label">{label}</span>
      {note && <span className="rl-counter-note">{note}</span>}
    </div>
  );
}

function Stat({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div>
      <div className="rl-stat-value">{value}</div>
      <div className="rl-stat-label">{label}</div>
      {note && <div className="rl-stat-note">{note}</div>}
    </div>
  );
}
