import { useMemo, useState } from "react";
import { verifyEntries, type ChainResult } from "./api";
import type { Dashboard, Step } from "../types";
import { shortHash } from "../entries";

/** Break the audit trail on purpose and watch it get caught.
 *
 * "Hash-chained" is the kind of claim everyone makes and nobody demonstrates.
 * This takes real entries out of the stored ledger, lets you edit one, and
 * posts them to the server, where the *production* `verify_chain_detail` runs
 * over them. Deliberately not verified in the browser: re-implementing SHA-256
 * in JavaScript would prove that the browser's copy works, which is not the
 * claim being made. */
export default function Chain({ data }: { data: Dashboard }) {
  const source = useMemo(() => {
    const c = data.cases.find((x) => x.timeline.length >= 5) ?? data.cases[0];
    return c ? c.timeline.slice(0, 8) : [];
  }, [data]);

  const [entries, setEntries] = useState<Step[]>(source);
  const [result, setResult] = useState<ChainResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [edited, setEdited] = useState<number | null>(null);

  const reset = () => {
    setEntries(source);
    setResult(null);
    setEdited(null);
  };

  const tamper = (i: number, kind: "payload" | "type" | "drop") => {
    setResult(null);
    setEntries((prev) => {
      if (kind === "drop") return prev.filter((_, j) => j !== i);
      return prev.map((e, j) => {
        if (j !== i) return e;
        if (kind === "type") return { ...e, type: "action_result" };
        return { ...e, payload: { ...e.payload, amount_at_risk: 1, tampered: true } };
      });
    });
    setEdited(i);
  };

  const verify = async () => {
    setBusy(true);
    try {
      // The dashboard flattens `entry_type` to `type` for display; the
      // verifier wants the ledger's own field names back.
      setResult(
        await verifyEntries(
          entries.map((e) => ({
            seq: e.seq,
            case_id: (e as any).case_id ?? data.cases[0]?.case_id,
            entry_type: e.type,
            payload: e.payload,
            timestamp: (e as any).timestamp,
            prev_hash: e.prev,
            hash: e.hash,
          })),
        ),
      );
    } finally {
      setBusy(false);
    }
  };

  if (source.length === 0) {
    return <p className="rl-empty-note">No stored ledger to work with.</p>;
  }

  return (
    <div className="rl-chain">
      <p className="rl-range-hint">
        These are real entries from the stored audit trail. Change one, then
        verify. The check runs server-side against the same
        <code> Ledger.verify_chain_detail </code> the agent uses.
      </p>

      <ul className="rl-chainlist">
        {entries.map((e, i) => (
          <li key={`${e.seq}-${i}`} className={edited === i ? "is-edited" : ""}>
            <span className="rl-chain-seq">#{e.seq}</span>
            <span className="rl-chain-type">{e.type}</span>
            <span className="rl-chain-hash">
              {shortHash(e.prev)} → {shortHash(e.hash)}
            </span>
            <span className="rl-chain-actions">
              <button onClick={() => tamper(i, "payload")}>edit payload</button>
              <button onClick={() => tamper(i, "type")}>change type</button>
              <button onClick={() => tamper(i, "drop")}>delete</button>
            </span>
          </li>
        ))}
      </ul>

      <div className="rl-range-actions">
        <button className="rl-btn rl-btn--primary" onClick={verify} disabled={busy}>
          {busy ? "Verifying…" : "Verify the chain"}
        </button>
        <button className="rl-btn" onClick={reset}>Restore</button>
      </div>

      {result && (
        <div className={`rl-verdict is-${result.ok ? "allow" : "deny"}`}>
          <span className="rl-verdict-decision">{result.ok ? "INTACT" : "BROKEN"}</span>
          <span className="rl-verdict-note">{result.detail}</span>
          {!result.ok && result.broken_at !== null && (
            <span className="rl-verdict-oracle is-bad">
              First bad entry: #{result.broken_at} · {result.failure?.replace(/_/g, " ")}
            </span>
          )}
        </div>
      )}

      {result && !result.ok && (
        <p className="rl-note">
          Every entry after the broken one is unverifiable too — that is the
          point of chaining. Editing a payload and recomputing that entry's own
          hash does not help either: the next entry still commits to the old
          one.
        </p>
      )}
    </div>
  );
}
