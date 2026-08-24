/* Client for the live console's backend (src/recovery_ledger/live/server.py).
 *
 * Everything here talks to the running agent. The static dashboard keeps
 * working with the server absent — `probe()` is how the UI finds out which
 * world it is in, and the Live section says so plainly rather than showing
 * dead controls.
 */

export type RuleName = string;

export type Citation = {
  kind: "circular" | "regulation" | "statute" | "policy";
  instrument: string | null;
  reference: string | null;
  clause: string | null;
  requirement: string;
  encoded_as: string;
  confidence: "primary" | "spec";
  note: string | null;
  url: string | null;
};

export type RosterCase = {
  index: number;
  case_id: string;
  loss_type: string;
  amount: number;
  language: string | null;
  is_b2b: boolean;
  tau_hat: number;
};

export type LiveEvent =
  | {
      type: "run_started";
      t_ms: number;
      run_id: string;
      seed: number;
      n_cases: number;
      policy: string;
      rules: RuleName[];
      uplift_correlation: number;
      train_seconds: number;
      roster: RosterCase[];
    }
  | {
      type: "ledger";
      t_ms: number;
      seq: number;
      case_id: string;
      entry_type: string;
      payload: Record<string, unknown>;
      hash: string;
      prev_hash: string;
    }
  | { type: "heartbeat"; t_ms: number }
  | { type: "run_finished"; t_ms: number; summary: RunSummary | null; error: string | null };

export type RunSummary = {
  cases: number;
  entries: number;
  recovered_rupees: number;
  resolved: number;
  stop_reasons: Record<string, number>;
  still_open: { case_id: string; resume_at: string }[];
  rounds_run: number;
  chain: ChainResult;
  killed: boolean;
  agent_ms: number;
  wall_ms: number;
  paced_ms: number;
};

export type ChainResult = {
  ok: boolean;
  checked?: number;
  broken_at: number | null;
  failure: string | null;
  detail: string;
  expected_hash?: string;
  stored_hash?: string;
};

export type AttackInfo = {
  name: string;
  category: string;
  intent: string;
  must_be_denied: boolean;
};

export type AttackResult = {
  attack: AttackInfo;
  decision: "ALLOW" | "DENY";
  action_type: string;
  channel: string | null;
  rules_evaluated: number;
  disabled_rules: RuleName[];
  correct: boolean;
  results: { rule: RuleName; passed: boolean; detail: Record<string, unknown>; citation: Citation | null }[];
  denied_by: { rule: RuleName; detail: Record<string, unknown>; citation: Citation | null }[];
  mutation?: {
    baseline_decision: string;
    mutated_decision: string;
    rule_was_load_bearing: boolean;
    note: string;
  };
  error?: string;
};

export type Lever = { key: string; label: string; description: string; expects: string };

export type Trace = {
  status: string;
  reason: string | null;
  paid: boolean;
  entries: { seq: number; entry_type: string; payload: Record<string, any>; hash: string }[];
  denials: { rule: RuleName; detail: Record<string, unknown>; citation: Citation | null }[];
};

export type Counterfactual = {
  case: {
    index: number;
    auto_picked: boolean;
    case_id: string;
    loss_type: string;
    amount: number;
    is_b2b: boolean;
    language: string;
    makes_contact: boolean;
  };
  lever: Lever;
  baseline: Trace;
  changed: Trace;
  diverged: boolean;
  note: string | null;
  error?: string;
};

async function post<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return (await r.json()) as T;
}

async function get<T>(path: string): Promise<T> {
  const r = await fetch(path);
  if (!r.ok) throw new Error(`${path} → ${r.status}`);
  return (await r.json()) as T;
}

export type Health = {
  ok: true;
  rules: RuleName[];
  attacks: number;
  levers: number;
  dist_built: boolean;
};

/** Is the live backend there? Resolves to null when it isn't — the static
 *  dashboard is a complete product without it, so absence is a state to
 *  render, not an error to throw. */
export async function probe(): Promise<Health | null> {
  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 2500);
    const r = await fetch("/api/health", { signal: controller.signal });
    clearTimeout(timer);
    if (!r.ok) return null;
    return (await r.json()) as Health;
  } catch {
    return null;
  }
}

export const startRun = (seed: number, n_cases: number, pace_ms: number) =>
  post<{ run_id: string; seed: number; n_cases: number; pace_ms: number }>("/api/run", {
    seed,
    n_cases,
    pace_ms,
  });

export const killRun = (run_id: string) =>
  post<{ run_id: string; engaged: boolean }>("/api/kill", { run_id });

export const getAttacks = () => get<{ attacks: AttackInfo[]; rules: RuleName[] }>("/api/attacks");

export const fireAttack = (name: string, disabled_rules: RuleName[]) =>
  post<AttackResult>("/api/attack", { name, disabled_rules });

export const getLevers = () =>
  get<{ levers: Lever[]; seed: number; roster: number }>("/api/levers");

export const runCounterfactual = (lever: string, seed: number, index: number | "auto") =>
  post<Counterfactual>("/api/counterfactual", { lever, seed, index });

export const verifyEntries = (entries: unknown[]) =>
  post<ChainResult>("/api/verify", { entries });

export const getProvenance = () => get<Record<RuleName, Citation>>("/api/provenance");

/** Subscribe to a run's event stream. Returns a function that closes it.
 *
 *  EventSource reconnects on its own after a drop, which would replay the
 *  backlog and duplicate every event in the UI. The server sends the backlog
 *  deliberately (so a late viewer sees the whole run) — so dedupe here on the
 *  server's own sequence numbers rather than fighting the reconnect. */
export function streamRun(
  runId: string,
  onEvent: (e: LiveEvent) => void,
  onClose?: () => void,
): () => void {
  const source = new EventSource(`/api/stream?run=${encodeURIComponent(runId)}`);
  const seenLedger = new Set<number>();
  let started = false;

  source.onmessage = (msg) => {
    let event: LiveEvent;
    try {
      event = JSON.parse(msg.data) as LiveEvent;
    } catch {
      return;
    }
    if (event.type === "heartbeat") return;
    if (event.type === "ledger") {
      if (seenLedger.has(event.seq)) return;
      seenLedger.add(event.seq);
    }
    if (event.type === "run_started") {
      if (started) return;
      started = true;
    }
    onEvent(event);
    if (event.type === "run_finished") {
      source.close();
      onClose?.();
    }
  };
  source.onerror = () => {
    if (source.readyState === EventSource.CLOSED) onClose?.();
  };

  return () => source.close();
}
