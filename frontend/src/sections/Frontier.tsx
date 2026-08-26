import { motion } from "motion/react";
import InView from "../motion/InView";
import type { Dashboard } from "../types";
import { money } from "../format";

/** Volume is not the lever.
 *
 * The spec calls a chart of the five baselines on incremental-₹-and-cost axes
 * "the single most persuasive frame in the video", and it is right, because
 * the argument is a *shape*: the policies that spend the most contacts are not
 * the ones that recover the most incremental money. A table of the same
 * numbers makes a reader do that comparison in their head. A plane makes it
 * immediate — up is money, right is messages sent, and the whole claim is that
 * you want to be up and to the left.
 *
 * Drawn as inline SVG from `data.json` rather than by embedding the matplotlib
 * PNG the experiment already writes. Three reasons, in increasing order of
 * importance: the PNG is light-themed on a dark page, it does not scale, and
 * — the one that matters — a PNG can go stale silently while the artifact
 * moves underneath it. Everything here is computed from the same JSON the
 * doc-consistency tests check, so this chart cannot disagree with RESULTS.md.
 *
 * The confidence intervals are drawn, not omitted. They are what makes the
 * honest version of this claim different from the flattering one: against
 * random targeting the intervals do not overlap, and against blind
 * mass-contact they do.
 */

// The spec's five, plus the matched-volume random control this project added
// as a falsification test. `ev_policy_lookahead` is the deployed policy — the
// one `make eval`, the dashboard and the live console all run.
const SHOWN = [
  { key: "do_nothing", label: "Do nothing", kind: "baseline" },
  { key: "razorpay_current", label: "Single retry, then halt", kind: "baseline" },
  { key: "random_targeting", label: "Random targeting", kind: "control" },
  { key: "rules_based_dunning", label: "Rules-based dunning", kind: "baseline" },
  { key: "blast_everyone", label: "Contact everyone", kind: "baseline" },
  { key: "ev_policy_lookahead", label: "This agent", kind: "ours" },
] as const;

type Point = {
  key: string;
  label: string;
  kind: string;
  contacts: number;
  point: number;
  lo: number;
  hi: number;
  dnd: number | null;
};

const W = 760;
const H = 460;
const PAD = { l: 78, r: 26, t: 24, b: 56 };

export default function Frontier({ data }: { data: Dashboard }) {
  const policies = data.baselines?.policies;
  if (!policies) return null;

  const byKey = new Map(policies.map((p: any) => [p.policy, p]));
  const pts: Point[] = [];
  for (const s of SHOWN) {
    const p: any = byKey.get(s.key);
    if (!p) continue;
    const inc = p.incremental_per_1000_cases;
    pts.push({
      key: s.key,
      label: s.label,
      kind: s.kind,
      contacts: p.contacts_sent,
      point: inc?.point ?? 0,
      lo: inc?.ci_low ?? 0,
      hi: inc?.ci_high ?? 0,
      dnd: p.pct_contacts_to_do_not_disturbs,
    });
  }
  if (pts.length < 3) return null;

  // Two of the baselines land on exactly the same coordinates, and it is not
  // a rendering accident: `rules_based_dunning` and `blast_everyone` are
  // byte-identical on every field in the artifact except their names. A fixed
  // three-message ladder that contacts everyone IS mass contact — the "rules"
  // discriminate between nobody. Merging them and saying so is more honest
  // than nudging one label aside, and it is the more useful observation.
  const merged: Point[] = [];
  const coincident: string[][] = [];
  for (const p of pts) {
    const twin = merged.find(
      (m) => Math.abs(m.contacts - p.contacts) < 1 && Math.abs(m.point - p.point) < 1,
    );
    if (twin) {
      const group = coincident.find((g) => g.includes(twin.label));
      if (group) group.push(p.label);
      else coincident.push([twin.label, p.label]);
      twin.label = `${twin.label} = ${p.label}`;
    } else {
      merged.push({ ...p });
    }
  }
  pts.length = 0;
  pts.push(...merged);

  const maxX = Math.max(...pts.map((p) => p.contacts)) * 1.12;
  const maxY = Math.max(...pts.map((p) => p.hi)) * 1.08;
  const x = (v: number) => PAD.l + (v / maxX) * (W - PAD.l - PAD.r);
  const y = (v: number) => H - PAD.b - (v / maxY) * (H - PAD.t - PAD.b);

  const ours = pts.find((p) => p.kind === "ours");
  const blast = pts.find((p) => p.key === "blast_everyone");
  const rand = pts.find((p) => p.key === "random_targeting");
  const overlapsBlast =
    ours && blast && !(ours.hi < blast.lo || blast.hi < ours.lo);
  const overlapsRandom =
    ours && rand && !(ours.hi < rand.lo || rand.hi < ours.lo);

  const yTicks = 4;

  return (
    <section className="rl-frontier">
      <div className="rl-frontier-inner">
        <p className="rl-sectionmark">The lever</p>
        <InView>
          <h2 className="rl-h2">
            Volume is not the lever.
            <span className="rl-dim">
              {" "}The policies that send the most messages are not the ones
              that recover the most incremental money.
            </span>
          </h2>
        </InView>

        <InView index={1}>
          <figure className="rl-chart">
            <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Incremental rupees recovered per 1,000 cases against messages sent, for six policies">
              {/* horizontal gridlines, one per tick */}
              {Array.from({ length: yTicks + 1 }, (_, i) => {
                const v = (maxY / yTicks) * i;
                return (
                  <g key={i}>
                    <line
                      x1={PAD.l} x2={W - PAD.r} y1={y(v)} y2={y(v)}
                      className="rl-chart-grid"
                    />
                    <text x={PAD.l - 10} y={y(v) + 4} className="rl-chart-tick" textAnchor="end">
                      {v === 0 ? "0" : `₹${Math.round(v / 1000)}k`}
                    </text>
                  </g>
                );
              })}

              {/* x axis */}
              <line x1={PAD.l} x2={W - PAD.r} y1={y(0)} y2={y(0)} className="rl-chart-axis" />
              {[0, 0.25, 0.5, 0.75, 1].map((f) => (
                <text
                  key={f}
                  x={x(maxX * f)}
                  y={H - PAD.b + 20}
                  className="rl-chart-tick"
                  textAnchor="middle"
                >
                  {Math.round((maxX * f) / 100) * 100}
                </text>
              ))}
              <text x={(PAD.l + W - PAD.r) / 2} y={H - 12} className="rl-chart-axislabel" textAnchor="middle">
                messages sent →
              </text>
              <text
                transform={`rotate(-90 16 ${(PAD.t + H - PAD.b) / 2})`}
                x={16}
                y={(PAD.t + H - PAD.b) / 2}
                className="rl-chart-axislabel"
                textAnchor="middle"
              >
                ↑ incremental ₹ per 1,000 cases
              </text>

              {/* the claim, drawn: up and to the left is better */}
              {ours && (
                <line
                  x1={x(ours.contacts)} y1={y(ours.point)}
                  x2={x(ours.contacts)} y2={y(0)}
                  className="rl-chart-drop"
                />
              )}

              {pts.map((p, i) => (
                <g key={p.key} className={`rl-chart-pt is-${p.kind}`}>
                  {/* the interval, not just the point */}
                  <line x1={x(p.contacts)} x2={x(p.contacts)} y1={y(p.lo)} y2={y(p.hi)} />
                  <motion.circle
                    cx={x(p.contacts)}
                    cy={y(p.point)}
                    r={p.kind === "ours" ? 7 : 5}
                    initial={{ scale: 0, opacity: 0 }}
                    whileInView={{ scale: 1, opacity: 1 }}
                    viewport={{ once: true }}
                    transition={{ delay: 0.15 + i * 0.07, duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
                  />
                  <text
                    x={x(p.contacts) + (p.contacts > maxX * 0.62 ? -12 : 12)}
                    y={y(p.point) - 10}
                    textAnchor={p.contacts > maxX * 0.62 ? "end" : "start"}
                  >
                    {p.label}
                  </text>
                  {p.dnd != null && (
                    <text
                      x={x(p.contacts) + (p.contacts > maxX * 0.62 ? -12 : 12)}
                      y={y(p.point) + 4}
                      textAnchor={p.contacts > maxX * 0.62 ? "end" : "start"}
                      className="rl-chart-sub"
                    >
                      {(p.dnd * 100).toFixed(1)}% to do-not-disturbs
                    </text>
                  )}
                </g>
              ))}
            </svg>
            <figcaption>
              Vertical bars are 95% confidence intervals on incremental
              recovery, from a paired bootstrap. Every figure is read from{" "}
              <code>results_baselines.json</code>.
              {coincident.length > 0 && (
                <>
                  {" "}
                  <b>
                    {coincident[0].join(" and ")} sit on the same point because
                    they are the same policy:
                  </b>{" "}
                  the artifact gives them identical values on every field but
                  their name. A fixed message ladder applied to everyone is
                  mass contact with extra steps — it discriminates between
                  nobody.
                </>
              )}
            </figcaption>
          </figure>
        </InView>

        {ours && rand && blast && (
          <InView index={2}>
            <div className="rl-frontier-reads">
              <div>
                <span className="rl-frontier-num">
                  {(ours.point / rand.point).toFixed(2)}x
                </span>
                <p>
                  more incremental revenue than contacting a{" "}
                  <b>comparable number of cases at random</b>, and the
                  intervals {overlapsRandom ? "overlap" : "do not overlap"}. That is
                  the targeting model earning its place — not contact volume.
                </p>
              </div>
              <div>
                <span className="rl-frontier-num">
                  {Math.round((1 - ours.contacts / blast.contacts) * 100)}%
                </span>
                <p>
                  fewer messages than contacting everyone, for{" "}
                  {overlapsBlast ? (
                    <>
                      <b>statistically indistinguishable</b> total recovery —
                      the intervals overlap, so "beats" would be an overclaim.
                    </>
                  ) : (
                    <>more total recovery, with non-overlapping intervals.</>
                  )}{" "}
                  The contact efficiency is the robust claim.
                </p>
              </div>
              <div>
                <span className="rl-frontier-num">
                  {money(ours.point / (ours.contacts / 2))}
                </span>
                <p>
                  of incremental recovery per message, against{" "}
                  {money(blast.point / (blast.contacts / 2))} for mass-contact.
                  Same plane, different economics.
                </p>
              </div>
            </div>
          </InView>
        )}
      </div>
    </section>
  );
}
