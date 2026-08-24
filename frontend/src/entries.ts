/* One-line renderings of ledger entries.
 *
 * Shared by the stored audit trail (CaseDetail) and the live console, so a
 * `decision` reads the same whether you are watching it happen or reading it
 * back a day later. Two different summarisers would eventually disagree, and
 * the whole claim of this project is that the record and the run are the same
 * thing. */

export type AnyEntry = { type?: string; entry_type?: string; payload?: Record<string, any> };

export function describeEntry(entry: AnyEntry): string {
  const p = entry.payload ?? {};
  switch (entry.type ?? entry.entry_type) {
    case "decision":
      return p.rationale ?? "";
    case "diagnosis":
      return p.narration ?? "";
    case "stop":
      return `reason: ${p.reason}`;
    case "pause":
      return `until ${p.resume_at}`;
    case "reply":
      return `customer intent: ${p.intent}`;
    case "action_result":
      return `${p.executed ? "executed" : "not executed"} ${p.action_type ?? ""}`;
    case "certificate": {
      const failed = (p.rule_results ?? [])
        .filter((r: any) => !r.passed)
        .map((r: any) => r.rule_name);
      return failed.length ? `denied by ${failed.join(", ")}` : "all rules passed";
    }
    case "case_ingested":
      return "case opened";
    default:
      return "";
  }
}

/** Certificates carry the decision; everything else is neutral. */
export function entryTone(entry: AnyEntry): "deny" | "allow" | "neutral" {
  const type = entry.type ?? entry.entry_type;
  if (type !== "certificate") return "neutral";
  return entry.payload?.decision === "DENY" ? "deny" : "allow";
}

export const shortHash = (h: string | undefined) => (h ?? "").slice(0, 10);
