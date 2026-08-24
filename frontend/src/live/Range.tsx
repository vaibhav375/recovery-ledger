import { useEffect, useMemo, useState } from "react";
import { fireAttack, getAttacks, type AttackInfo, type AttackResult, type Citation } from "./api";
import { titleise } from "../format";

/** The Kernel Range.
 *
 * A block rate in a report is a claim. A refusal you triggered yourself, with
 * the rule that refused it and the instrument behind that rule, is evidence.
 * The mutation switches are the more important half: turn off the rule that
 * was doing the refusing, fire the same attack, and watch it land. A suite
 * that cannot fail proves nothing. */
export default function Range() {
  const [attacks, setAttacks] = useState<AttackInfo[]>([]);
  const [rules, setRules] = useState<string[]>([]);
  const [selected, setSelected] = useState<string>("");
  const [disabled, setDisabled] = useState<string[]>([]);
  const [result, setResult] = useState<AttackResult | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    getAttacks()
      .then((d) => {
        setAttacks(d.attacks);
        setRules(d.rules);
        setSelected(d.attacks[0]?.name ?? "");
      })
      .catch(() => undefined);
  }, []);

  const byCategory = useMemo(() => {
    const map = new Map<string, AttackInfo[]>();
    for (const a of attacks) {
      const list = map.get(a.category) ?? [];
      list.push(a);
      map.set(a.category, list);
    }
    return [...map.entries()];
  }, [attacks]);

  const current = attacks.find((a) => a.name === selected);

  const fire = async () => {
    if (!selected) return;
    setBusy(true);
    try {
      setResult(await fireAttack(selected, disabled));
    } finally {
      setBusy(false);
    }
  };

  const toggleRule = (r: string) =>
    setDisabled((d) => (d.includes(r) ? d.filter((x) => x !== r) : d.concat(r)));

  return (
    <div className="rl-range">
      <div className="rl-range-split">
        <div>
          <div className="rl-live-head">
            <span>Attack</span>
            <span className="rl-live-head-meta">{attacks.length} in the suite</span>
          </div>
          <select
            className="rl-select"
            value={selected}
            onChange={(e) => { setSelected(e.target.value); setResult(null); }}
          >
            {byCategory.map(([cat, list]) => (
              <optgroup key={cat} label={cat}>
                {list.map((a) => (
                  <option key={a.name} value={a.name}>{a.name.replace(/_/g, " ")}</option>
                ))}
              </optgroup>
            ))}
          </select>
          {current && <p className="rl-range-intent">{current.intent}</p>}

          <div className="rl-live-head" style={{ marginTop: 26 }}>
            <span>Mutation</span>
            <span className="rl-live-head-meta">switch a rule off</span>
          </div>
          <p className="rl-range-hint">
            Removing a rule and firing the same attack is how you find out
            whether the rule was doing the work, or whether the suite was
            passing for free.
          </p>
          <div className="rl-rulepicker">
            {rules.map((r) => (
              <button
                key={r}
                type="button"
                aria-pressed={disabled.includes(r)}
                onClick={() => toggleRule(r)}
              >
                {r}
              </button>
            ))}
          </div>

          <div className="rl-range-actions">
            <button className="rl-btn rl-btn--primary" onClick={fire} disabled={busy || !selected}>
              {busy ? "Firing…" : "Fire at the kernel"}
            </button>
            {disabled.length > 0 && (
              <button className="rl-btn" onClick={() => setDisabled([])}>
                Restore {disabled.length} rule{disabled.length > 1 ? "s" : ""}
              </button>
            )}
          </div>
        </div>

        <div>
          {!result ? (
            <p className="rl-empty-note">
              Pick an attack and fire it. This runs the same
              <code> redteam/attacks.py </code> definitions <code>make redteam</code>{" "}
              runs, against the same kernel.
            </p>
          ) : result.error ? (
            <p className="rl-note is-error">{result.error}</p>
          ) : (
            <>
              <div className={`rl-verdict is-${result.decision.toLowerCase()} ${result.correct ? "" : "is-leak"}`}>
                <span className="rl-verdict-decision">{result.decision}</span>
                <span className="rl-verdict-note">
                  {result.decision === "DENY"
                    ? "The kernel refused this action before it could execute."
                    : "The kernel permitted this action."}
                </span>
                <span className={`rl-verdict-oracle ${result.correct ? "is-ok" : "is-bad"}`}>
                  {result.correct
                    ? "Matches the oracle"
                    : "Disagrees with the oracle — this is a leak"}
                </span>
              </div>

              {result.mutation && (
                <p className={`rl-note ${result.mutation.rule_was_load_bearing ? "is-error" : "is-alert"}`}>
                  <strong>
                    With every rule: {result.mutation.baseline_decision}. Without{" "}
                    {result.disabled_rules.join(", ")}: {result.mutation.mutated_decision}.
                  </strong>{" "}
                  {result.mutation.note}
                </p>
              )}

              {result.denied_by.length > 0 && (
                <div className="rl-cited">
                  {result.denied_by.map((d) => (
                    <CitationCard key={d.rule} rule={d.rule} citation={d.citation} detail={d.detail} />
                  ))}
                </div>
              )}

              <div className="rl-live-head" style={{ marginTop: 22 }}>
                <span>All {result.rules_evaluated} rules</span>
                <span className="rl-live-head-meta">
                  {result.disabled_rules.length > 0
                    ? `${result.disabled_rules.length} switched off`
                    : "full kernel"}
                </span>
              </div>
              <ul className="rl-rulelist">
                {result.results.map((r) => (
                  <li key={r.rule} className={r.passed ? "is-pass" : "is-fail"}>
                    <code>{r.rule}</code>
                    <span>{r.passed ? "pass" : "refused"}</span>
                  </li>
                ))}
                {result.rules_evaluated === 0 && (
                  <li className="is-fail">
                    <code>—</code>
                    <span>no rules registered: deny by default</span>
                  </li>
                )}
              </ul>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

export function CitationCard({
  rule, citation, detail,
}: { rule: string; citation: Citation | null; detail?: Record<string, unknown> }) {
  if (!citation) return <div className="rl-citation"><code>{rule}</code></div>;
  const isPolicy = citation.kind === "policy";
  return (
    <div className={`rl-citation ${isPolicy ? "is-policy" : ""}`}>
      <div className="rl-citation-head">
        <code>{rule}</code>
        <span className="rl-citation-kind">{isPolicy ? "internal policy" : citation.kind}</span>
      </div>
      {citation.instrument ? (
        <p className="rl-citation-instrument">
          {citation.instrument}
          {citation.reference && <span className="rl-dim"> · {citation.reference}</span>}
          {citation.clause && <span className="rl-dim"> · {citation.clause}</span>}
        </p>
      ) : (
        <p className="rl-citation-instrument rl-dim">
          Not law. This is this project's own operating limit.
        </p>
      )}
      <p className="rl-citation-req">{citation.requirement}</p>
      <p className="rl-citation-enc">
        <span className="rl-dim">Encoded as: </span>
        {citation.encoded_as}
      </p>
      {citation.confidence === "spec" && (
        <p className="rl-citation-flag">
          Clause number not pinned. This rule was encoded from the project
          spec's summary of the requirement; the instrument above is our
          identification of it. Recorded rather than invented.
        </p>
      )}
      {citation.note && <p className="rl-citation-note">{citation.note}</p>}
      {detail && Object.keys(detail).length > 0 && (
        <pre className="rl-citation-detail">{JSON.stringify(detail, null, 1)}</pre>
      )}
      {citation.url && (
        <a className="rl-citation-link" href={citation.url} target="_blank" rel="noreferrer">
          {new URL(citation.url).hostname} ↗
        </a>
      )}
    </div>
  );
}

export { titleise };
