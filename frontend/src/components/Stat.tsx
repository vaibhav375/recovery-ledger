export default function Stat({
  label, value, note, tone,
}: {
  label: string;
  value: string | number;
  note?: string;
  tone?: "ok" | "deny";
}) {
  return (
    <div className="card rl-stat">
      <div className="rl-stat-label">{label}</div>
      <div className={`rl-stat-value${tone ? ` is-${tone}` : ""}`}>{value}</div>
      {note && <div className="rl-stat-note">{note}</div>}
    </div>
  );
}
