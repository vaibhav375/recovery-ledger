import InView from "../motion/InView";
import type { Dashboard } from "../types";
import { money } from "../format";
import CautionCurve from "../components/CautionCurve";

/** The four experiments in which this project is the thing under test.
 *
 * Everything above this section measures the agent. This measures the
 * measurement — and three of the four found something wrong with the project
 * rather than with the world. That is the reason they are on the page instead
 * of in JSON nobody opens: a result that only ever confirms you is not
 * evidence that you checked.
 *
 * Each card leads with what was found, not with what was run. Where a finding
 * corrected a number this project had already published, it says so and shows
 * the old value — a correction that hides the thing it corrected is just a
 * quieter version of the original mistake.
 */
export default function Audit({ data }: { data: Dashboard }) {
  const { ope, fairness, pessimism, dnd_signal: dnd } = data;
  if (!ope && !fairness && !pessimism && !dnd) return null;

  return (
    <section className="rl-audit">
      <div className="rl-audit-inner">
        <p className="rl-sectionmark">The audit</p>
        <InView>
          <h2 className="rl-h2">
            Four experiments where the system under test is this one.
            <span className="rl-dim">
              {" "}Three of them found something wrong with it.
            </span>
          </h2>
        </InView>

        <div className="rl-audit-grid">
          {ope && <OffPolicy ope={ope} />}
          {dnd && <DndSignal dnd={dnd} />}
          {pessimism && <Pessimism p={pessimism} />}
          {fairness && <Fairness f={fairness} />}
        </div>
      </div>
    </section>
  );
}

/* ── can we value a policy we never ran? ─────────────────────────────── */

function OffPolicy({ ope }: { ope: any }) {
  const at = (metric: string, eps: number) =>
    (ope.replication_study ?? []).find(
      (r: any) => r.metric === metric && r.epsilon === eps,
    );
  const bounded = at("payment_rate", 0.1);
  const money_ = at("net_value", 0.1);
  const reps = ope.replications_per_epsilon;
  if (!bounded || !money_) return null;

  return (
    <Card
      mark="Off-policy evaluation"
      title="The estimator is sound. The money is not estimable."
      finding="found a limit"
    >
      <p>
        Value a rule you never deployed from the logs of the one you did, then
        check it against the truth. {reps} logging draws.
      </p>
      <table className="rl-audit-table">
        <thead>
          <tr>
            <th>at ε = 0.10</th>
            <th className="rl-num">interval covers truth</th>
            <th className="rl-num">picks the best policy</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>payment rate (bounded)</td>
            <td className="rl-num rl-pass">{pct(bounded.coverage.SNIPS)}</td>
            <td className="rl-num rl-pass">
              {Math.round(bounded.ranking_agreement * reps)} / {reps}
            </td>
          </tr>
          <tr>
            <td>net rupees (heavy-tailed)</td>
            <td className="rl-num rl-hi">{pct(money_.coverage.SNIPS)}</td>
            <td className="rl-num rl-hi">
              {Math.round(money_.ranking_agreement * reps)} / {reps}
            </td>
          </tr>
        </tbody>
      </table>
      <p className="rl-audit-note">
        Nominal coverage is 95%. One opt-out on a large subscription outweighs
        the gap between two policies, so the rupee estimate carries no coverage
        guarantee — choose policies on the bounded outcome. Without exploration
        the logs describe only themselves: one policy of six is identified.
      </p>
    </Card>
  );
}

/* ── the number that did not survive a bigger sample ─────────────────── */

function DndSignal({ dnd }: { dnd: any }) {
  const small = (dnd.stability_by_sample_size ?? []).find((r: any) => r.n === 5000);
  return (
    <Card
      mark="Novelty claim N2"
      title="A published figure measured where it swings by more than its own size."
      finding="corrected our own claim"
    >
      <p>
        How much more do-not-disturbs opt out when contacted — the signal N2
        rests on. Published as{" "}
        <span className="rl-audit-was">1.93x</span> from one n = 5,000 draw.
      </p>
      <div className="rl-audit-figure">
        <span className="rl-audit-value">{dnd.ratio.toFixed(2)}x</span>
        <span className="rl-audit-ci">
          95% CI {dnd.ci_low.toFixed(2)}–{dnd.ci_high.toFixed(2)} at n ={" "}
          {dnd.headline_n.toLocaleString("en-IN")}
        </span>
      </div>
      {small && (
        <p className="rl-audit-note">
          At n = 5,000 the ratio ranges{" "}
          <b>
            {Math.min(...small.ratios).toFixed(2)}x–
            {Math.max(...small.ratios).toFixed(2)}x
          </b>{" "}
          across seeds — wider than the effect, landing on both sides of 1.0.
          The claim survives in direction, not magnitude: the interval excludes
          1.0, and opt-out without contact is exactly{" "}
          {dnd.opt_out_rate_without_contact.toFixed(4)}.
        </p>
      )}
    </Card>
  );
}

/* ── acting on a lower bound ─────────────────────────────────────────── */

function Pessimism({ p }: { p: any }) {
  const draws = p.draws ?? [];
  if (!draws.length) return null;
  const ks = draws[0].sweep.map((r: any) => r.uncertainty_k);
  const mean = (i: number, f: string) =>
    draws.reduce((a: number, d: any) => a + d.sweep[i][f], 0) / draws.length;
  const i0 = 0;
  const ib = ks.indexOf(0.5) >= 0 ? ks.indexOf(0.5) : 1;
  const gains = p.improvement_per_case_per_draw ?? [];

  return (
    <Card
      mark="Caution"
      title="Acting on a lower bound, not a point estimate."
      finding="fixed what the audit found"
    >
      <p>
        τ̂ = 0.02 from a model that understands a segment and τ̂ = 0.02 from one
        that is guessing decide identically. So the policy acts on{" "}
        <code>τ̂ − k·se</code> instead.
      </p>
      <CautionCurve draws={draws} />
      <p className="rl-audit-note">
        At k = 0.5 the agent sends <b>{mean(ib, "contacts").toFixed(0)}</b> messages instead of{" "}
        <b>{mean(i0, "contacts").toFixed(0)}</b> and lifts value per contact from{" "}
        {money(mean(i0, "net_value_per_contact"))} to{" "}
        <b>{money(mean(ib, "net_value_per_contact"))}</b>. But net value moves only{" "}
        {money(Math.min(...gains))}–{money(Math.max(...gains))} per case, and
        the best k is <b>not stable</b> across draws ({p.best_k_per_draw.join(", ")}) — a single
        draw called this a clean +7.4% win. Caution keeps buying harm reduction
        long after it stops buying money.
      </p>
    </Card>
  );
}

/* ── who does the agent decline to help? ─────────────────────────────── */

function Fairness({ f }: { f: any }) {
  const segs = f.segments ?? {};
  const flagged = Object.entries(segs).filter(([, v]: any) => v.unexplained);
  const b2b = segs.b2b?.groups ?? {};
  const q1 = segs.amount_quartile?.groups?.Q1;

  return (
    <Card
      mark="Disparity audit"
      title={
        flagged.length
          ? "An unexplained disparity."
          : "No unexplained disparity — and that is not the finding."
      }
      finding="found what rates cannot see"
    >
      <p>
        Contact rates by language, B2B status, amount and loss type, over{" "}
        {f.n_permutations?.toLocaleString("en-IN")} label permutations.
      </p>
      <table className="rl-audit-table">
        <thead>
          <tr>
            <th>group</th>
            <th className="rl-num">contact rate</th>
            <th className="rl-num">model correlation</th>
          </tr>
        </thead>
        <tbody>
          {b2b.b2b && (
            <tr>
              <td>B2B</td>
              <td className="rl-num">{b2b.b2b.contact_rate.toFixed(3)}</td>
              <td className="rl-num rl-hi">{b2b.b2b.model_correlation.toFixed(2)}</td>
            </tr>
          )}
          {b2b.b2c && (
            <tr>
              <td>B2C</td>
              <td className="rl-num">{b2b.b2c.contact_rate.toFixed(3)}</td>
              <td className="rl-num">{b2b.b2c.model_correlation.toFixed(2)}</td>
            </tr>
          )}
          {q1 && (
            <tr>
              <td>smallest invoices</td>
              <td className="rl-num">{q1.contact_rate.toFixed(3)}</td>
              <td className="rl-num rl-hi">{q1.model_correlation.toFixed(2)}</td>
            </tr>
          )}
        </tbody>
      </table>
      <p className="rl-audit-note">
        No gap survives conditioning. The problem is elsewhere: <b>the policy
        acts most confidently on the segments the model understands least</b>.
        B2B gets the highest contact rate and the worst correlation with truth;
        the smallest invoices correlate at essentially zero and are contacted
        more than the quartiles the model reads best. An audit that only checks
        contact rates passes that without comment.
      </p>
    </Card>
  );
}

/* ── shared ──────────────────────────────────────────────────────────── */

function Card({
  mark, title, finding, children,
}: {
  mark: string;
  title: string;
  finding: string;
  children: React.ReactNode;
}) {
  return (
    <InView>
      <article className="rl-audit-card">
        <header>
          <span className="rl-audit-mark">{mark}</span>
          <span className="rl-audit-finding">{finding}</span>
        </header>
        <h3>{title}</h3>
        {children}
      </article>
    </InView>
  );
}

const pct = (v: number | null | undefined) =>
  v == null ? "—" : `${Math.round(v * 100)}%`;
