export type Step = {
  type: string;
  seq: number;
  case_id: string;
  timestamp: string;
  // Full SHA-256, not a display prefix: the chain verifier re-derives these,
  // so a truncated hash would make the stored trail unverifiable.
  hash: string;
  prev: string;
  payload: Record<string, any>;
};

export type CaseCard = {
  case_id: string;
  loss_type: string;
  amount: number;
  language: string;
  channel: string;
  is_b2b: boolean;
  outcome: string;
  denied: number;
  certificates: number;
  timeline: Step[];
};

export type RuleStat = {
  rule: string;
  evaluated: number;
  passed: number;
  failed: number;
};

export type Summary = {
  cases: number;
  entries: number;
  certificates: number;
  denied: number;
  executed_actions: number;
  stop_reasons: Record<string, number>;
};

export type Dashboard = {
  source: string;
  summary: Summary;
  cases: CaseCard[];
  rule_stats: RuleStat[];
  fleet: any | null;
  negotiation: any[] | null;
  listener: any | null;
  baselines: any | null;
  batch: any | null;
  sensitivity: any | null;
  rule_provenance?: Record<string, import("./live/api").Citation>;
};
