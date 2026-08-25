# Who does this agent decide not to help?

```
make fairness
```

The compliance kernel checks whether an **action** is permitted. Nothing else
in this project checks whether the **policy** distributes its attention
fairly. Those are different questions, and passing the first does not answer
the second: an agent can refuse every illegal action and still systematically
decline to work one group's cases.

## What would count as a violation

In collections the harm runs both ways, so this audit reports both rather than
picking whichever framing flatters the system.

- **Under-contact is denied access to resolution.** A case the agent never
  works loses whatever chance the contact would have created.
- **Over-contact is a larger share of the pressure.** The RBI recovery norms
  exist because collection contact is a burden.

Neither is automatically wrong. What would be wrong is a gap with no basis, so
the whole analysis is built around one question: **is the difference in how
groups are treated explained by a real difference in how much contact actually
helps them?**

Raw gaps prove nothing — the policy contacts on expected value, which is
predicted uplift times amount, so a group with larger invoices *should* be
contacted more. Every test below conditions on predicted uplift crossed with
amount, the two quantities the objective is entitled to use. Because this is a
simulator, one further check is available that no production audit can run:
within the same cells, does the *true* benefit differ? If treatment differs and
true benefit does not, the model invented the difference.

## Result: no unexplained disparity in any segment

4,000 cases, 2,000 permutations, 16 hypotheses, Bonferroni α = 0.0031.

| segment | contact gap (excess over null) | p | true-benefit gap | p | verdict |
|---|---:|---:|---:|---:|---|
| language | +0.017 | 0.080 | +₹30 | 0.046 | no significant gap |
| B2B / B2C | +0.056 | 0.001 | +₹87 | 0.001 | explained |
| amount quartile | +0.146 | 0.001 | +₹209 | 0.001 | explained |
| loss type | +0.476 | 0.001 | +₹172 | 0.004 | explained |

The language result is the one that mattered most going in, and it is clean:
contact rates run 21–28% across English, Hindi, Hinglish and regional
speakers, and the gap does not survive conditioning.

**The detector is not simply incapable of firing.**
`tests/test_fairness_audit.py` plants a 25-point within-cell disparity and
requires it to be caught, and plants a gap fully explained by the conditioning
and requires it *not* to be. A clean audit from a detector that never fires
would be worthless.

## What the audit found instead: the model is not equally good at everyone

Correlation between predicted and true uplift, by group:

| segment | group | correlation | contact rate |
|---|---|---:|---:|
| B2B | **b2b** | **0.11** | 0.311 |
| | b2c | 0.36 | 0.241 |
| amount | **Q1 (smallest)** | **0.09** | 0.302 |
| | Q2 | 0.23 | 0.348 |
| | Q3 | 0.33 | 0.132 |
| | Q4 (largest) | 0.32 | 0.227 |
| language | en / hi / hinglish / regional | 0.31 – 0.35 | 0.21 – 0.28 |

Language is even. The other two are not, and the pattern is uncomfortable:

**The policy acts most confidently on the segments the model understands
least.** B2B cases get the *highest* contact rate (31.1% against 24.1%) and
have the *worst* model correlation (0.11 against 0.36). The smallest invoices,
Q1, have a correlation of 0.09 — effectively no signal — and are contacted
more than the two quartiles the model reads best.

This is not disparate treatment. It is something the treatment-rate tests
cannot see: **epistemic** inequality. Every decision made for a B2B customer
rests on an estimate barely better than noise, and the audit that only checks
contact rates would pass it without comment.

## Two targeting failures the audit surfaced

Descriptive, not significance-tested — reported because they are visible in
the group means and worth acting on.

- **Amount Q2 and Q3 are the wrong way round.** Q3 has the highest true value
  of contact in the book (₹353 per case) and the *lowest* contact rate
  (13.2%). Q2 is worth ₹239 and gets the highest contact rate (34.8%).
- **Overdue receivables have negative true value** (−₹69 per case: contacting
  them destroys more through opt-outs than it recovers) and are still
  contacted 20.2% of the time.

The `attention_aligned_with_true_value` field in the JSON reports the rank
correlation between a segment's contact rates and its true values. It is
**descriptive only** — a rank correlation over two to four points carries
essentially no statistical weight, and no test is attached to it.

## Two methodology errors found while building this

Both would have produced a confident wrong answer, and neither raises.

**The gap statistic could not report zero.** `_cell_gap` is a max-minus-min
across groups, so it is bounded below by sampling noise. Over thirty thin
cells with four language groups, the *conditional* gap came out at 0.209
against a raw unconditional gap of 0.056 — conditioning appeared to reveal a
disparity four times larger than the one visible without it. The p-value was
always valid; the effect size printed beside it was noise. The statistic now
reports `excess` over the permutation null's mean, and the cells are coarser.

**The multiple-comparison correction was applied to the wrong test.** A
verdict of "unexplained" needs a real treatment gap *and* no real difference
in benefit. Correcting the threshold on the second makes it harder to find an
explanation, which makes crying wolf easier — the opposite of what a
correction is for. With the correction on both, `loss_type` was flagged as an
unexplained disparity on a true-benefit p of 0.004 against a corrected 0.0031,
while the observed benefit gap was +₹172. That is a non-significant p read as
evidence of absence, at a threshold chosen to make absence easier to conclude.
The disparity test now clears the corrected bar; the explanation test clears
an ordinary 0.05.

## One more, about what "contact" means

The first version measured only customer contact and reported failed
subscriptions at 0.9% — apparently the most neglected group in the book. They
are not: the policy works **100%** of them, by silent retry, because a
subscription can be re-charged without messaging anyone. Measuring contact
alone read correct channel choice as neglect.

The audit now reports both `contact_rate` and `worked_rate`. It is the same
distinction the compliance kernel already makes when it exempts RETRY and WAIT
from the contact-hours rule: a background retry does not reach the customer.

## Reproducing

```
make fairness      # ~10 minutes at the default 2,000 permutations
```

Deterministic given the seeds in the script.
