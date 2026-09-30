---
title: Recovery Ledger — live console
emoji: 📒
colorFrom: gray
colorTo: green
sdk: docker
app_port: 7860
pinned: false
license: mit
---

# Recovery Ledger, reachable

The static dashboard at
[vaibhav375.github.io/recovery-ledger](https://vaibhav375.github.io/recovery-ledger/)
is a complete report: every number on it comes from runs that already happened,
and it needs no server.

This is the part that is not a report. It drives the running system:

- **Run it** — start the agent and watch the loop write its own audit trail.
- **Attack it** — fire the red-team suite at the compliance kernel, one attack
  at a time, with rules you choose switched off.
- **Change one fact** — the same case, run twice, with one fact of the world
  different.
- **Break the trail** — tamper with a ledger entry and watch chain verification
  catch it.

Source: [github.com/vaibhav375/recovery-ledger](https://github.com/vaibhav375/recovery-ledger)

The models are fitted when the container starts, so the first request after a
cold start waits a few seconds. Everything after it is the agent's own speed.
