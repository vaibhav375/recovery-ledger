---
title: Recovery Ledger — live console
emoji: 📒
colorFrom: gray
colorTo: green
sdk: gradio
app_file: app.py
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

The models are fitted when the Space starts, so the first request after a cold
start waits a few seconds. Everything after it is the agent's own speed.

Running under the Gradio SDK rather than Docker, which Hugging Face charges
for. `app.py` starts the same console server that runs locally and the Space
serves whatever is listening on 7860; no Gradio app is involved. The Dockerfile
beside it is still current, for hosts that build images for free.
