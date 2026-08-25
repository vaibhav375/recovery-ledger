# Can we value a policy we never deployed?

```
make ope
```

Tier 1 proved the off-policy estimators recover a known answer on real
randomised data. That establishes the *method*. It does not establish the
thing an operator actually wants, which is:

> Before I ship a new targeting rule, can you tell me what it would have
> earned — from data I already have — without testing it on customers?

This experiment answers that and then checks the answer, which is only
possible because the simulator can be asked to run the counterfactual.

1. Deploy the EV policy with **ε-greedy exploration**. Log the features, the
   action, the propensity score P(contact | x), and the outcome.
2. Take six candidate policies, none of which were deployed. Estimate each
   one's value **from the logs alone**.
3. Actually run each candidate on the same cases under common random numbers,
   and measure what it really earns.
4. Compare, over **20 independent logging draws per ε**, because coverage
   from a single log is a coin flip.

## What is and is not being evaluated

The decision here is the single targeting decision — contact this case or do
not — taken once per case at attempt 0. That is the decision the uplift model
informs and the one the Tier 1 estimators were validated for.

It is **not** full-sequence off-policy evaluation of the multi-step agent
loop. Importance weights compound along a trajectory, and a three-step
sequence needs sequential estimators this project has not validated. The
contextual-bandit framing is a real limitation, stated here and everywhere
these numbers are quoted.

## The objective

    value = paid × amount − channel cost − λ_churn × LTV if they opted out

Evaluated on realised outcomes, not on the model's beliefs about them. This is
the objective the deployed policy optimises, and using it matters: channel
costs are pennies against four-figure invoices, so under a **payment-rate**
objective "contact everyone" wins by construction and targeting has nothing to
prove. Both metrics are reported below, and the difference between them turns
out to be the finding.

## Result 1 — without exploration, the logs can only describe themselves

At ε = 0 the deployed policy is deterministic. For every case, one of the two
actions had probability zero, so for any policy that disagrees anywhere the
estimand is **not identified**: no amount of data recovers it.

| ε | policies identified | policies with usable overlap |
|---:|---:|---:|
| 0.00 | 1 / 6 | 1 / 6 |
| 0.05 | 6 / 6 | 4 / 6 |
| 0.10 | 6 / 6 | 6 / 6 |
| 0.20 | 6 / 6 | 6 / 6 |
| 0.40 | 6 / 6 | 6 / 6 |

The one identified policy at ε = 0 is the deployed policy itself — evaluating
a policy on its own logs, which is not evaluation.

**This is why the check is not effective sample size.** At ε = 0 the agreeing
rows are numerous and evenly weighted, so ESS looks healthy while the estimate
is answering a different question: the value of the target policy *restricted
to the sub-population the logger happened to agree with*. An early version of
`overlap_report` judged on ESS alone and called those logs usable.
`tests/test_ope_deployment.py::test_ess_alone_would_have_called_an_unidentified_log_usable`
now fails the build if that regresses.

## Result 2 — the estimator is sound; the money is the problem

Nominal coverage is 95%. Over 20 independent logging draws × 6 policies:

| ε | coverage, payment rate | coverage, net ₹ | picks the best policy, payment rate | picks the best policy, net ₹ |
|---:|---:|---:|---:|---:|
| 0.05 | 92% | 69% | 18 / 20 | 5 / 20 |
| 0.10 | 100% | 69% | 20 / 20 | 7 / 20 |
| 0.20 | 98% | 77% | 20 / 20 | 13 / 20 |
| 0.40 | 95% | 87% | 20 / 20 | 13 / 20 |

On the **bounded** outcome the estimators behave exactly as advertised: at
ε = 0.10 the interval covers the truth every time, and the logs identify the
truly best-performing policy in 20 runs out of 20.

On **net rupees** they do not. Coverage sits at 69–87% against a nominal 95%,
and at ε = 0.10 the logs pick the truly best policy about a third of the time.

The cause is the tail, not the method. One opt-out on a large subscription
costs `λ_churn × 6 × invoice` — a single case can move the mean by more than
the entire difference between two policies. Importance-weight that, and the
bootstrap interval is being drawn around a handful of rows. The pattern
confirms it: mean absolute error falls monotonically as exploration rises
(₹231 → ₹147 → ₹120 → ₹92 for ε = 0.05 → 0.40), which is variance shrinking,
not bias being corrected.

**So the honest operating rule is: choose policies on the bounded outcome, and
treat the rupee figure as an estimate with no coverage guarantee.** That is a
narrower claim than "we can evaluate policies offline", and it is the one the
measurements support.

## Result 3 — what exploration costs

At ε = 0.10 the logged policy earned ₹206 per case against the deployed
policy's ₹227 — about **₹20 per case**, or 9% of the objective, to buy the
ability to value any future policy from the same logs.

That is a real price and it should be stated as one. It is also the choice
every recovery system makes implicitly: a system that never explores is not
saving the 9%, it is paying it later as the cost of A/B testing each change on
live customers, without an audit trail and without a confidence interval.

## Why the single-seed run would have misled us

The first version of this experiment ran one logging draw per ε. At ε = 0.10
it reported every interval covering the truth and the ranking agreeing — a
clean pass. Replication shows that was luck: the real coverage at that setting
is 69% and the ranking agrees 35% of the time.

Nothing about the code changed between those two conclusions. Only the number
of times it was run.

## Reproducing

```
make ope       # ~4 minutes; writes results_ope_deployment.json
```

Deterministic given the seeds in the script. Run it twice and diff the JSON.
