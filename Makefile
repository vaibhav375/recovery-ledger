.PHONY: setup test tier1-hillstrom tier1-criteo demo eval baselines sensitivity redteam dashboard listener-eval fleet negotiate frontend-build dashboard-serve frontend-dev live ope fairness pessimism dnd-signal verify-page horizon dr-diagnosis dr-foldsweep uplift-ab lambda-sweep regret

# `uv pip install` honours an ambient VIRTUAL_ENV over the venv it was just
# told to create. Anyone who runs `make setup` with another virtualenv active
# — which is most people, most of the time — gets `uv venv` making ./.venv and
# then `uv pip install` putting every dependency somewhere else. It exits 0.
# The repo's venv is left empty and every later target dies on
# `ModuleNotFoundError: No module named 'pydantic'`, several commands after
# the one that actually failed. It also silently rewrites the OTHER
# environment's editable install, which is how this was found.
#
# `--python .venv/bin/python3` names the target explicitly, so the ambient
# variable cannot win. Verified by tests/test_makefile_setup.py.
setup:
	uv venv --python 3.12
	uv pip install --python .venv/bin/python3 -e ".[dev]"
	@# macOS only, and non-fatal. uv writes .pth files with the UF_HIDDEN flag
	@# set, and CPython's site.addpackage skips hidden .pth files without a
	@# word (site.py: "Skipping hidden .pth file"). The editable install is
	@# therefore installed correctly and silently never on sys.path, so
	@# `import recovery_ledger` fails in a plain REPL while every make target
	@# works, because they all set PYTHONPATH=src. Clearing the flag makes the
	@# editable install behave the way `pip install -e` is supposed to.
	@if [ "$$(uname)" = "Darwin" ]; then \
		chflags nohidden .venv/lib/python*/site-packages/*.pth 2>/dev/null || true; \
	fi
	@.venv/bin/python3 -c "import pydantic, numpy, sklearn, pandas" \
		|| (echo "setup FAILED - .venv is missing dependencies"; exit 1)
	@.venv/bin/python3 -c "import recovery_ledger" 2>/dev/null \
		&& echo "setup OK - dependencies and recovery_ledger importable from .venv" \
		|| echo "setup OK - dependencies installed (editable import needs PYTHONPATH=src, which every make target sets)"

test:
	.venv/bin/python3 -m pytest -v

# Tier 1 validation (spec section 7.2) — the kill gate. See
# experiments/tier1_criteo/REPORT.md for the last recorded results.
tier1-hillstrom:
	PYTHONPATH=src .venv/bin/python3 experiments/tier1_criteo/run_validation.py \
		--dataset hillstrom --target-col visit

tier1-criteo:
	PYTHONPATH=src .venv/bin/python3 experiments/tier1_criteo/run_validation.py \
		--dataset criteo --sample-frac 0.02 --target-col visit

uplift-ab:
	PYTHONPATH=src .venv/bin/python3 experiments/uplift_ab/run_uplift_ab.py \
		--n-eval 2000 --eval-draws 5

calibration:
	PYTHONPATH=src .venv/bin/python3 experiments/uplift_calibration/run_calibration.py \
		--n-train 5000 --n-eval 4000 --eval-draws 3

regret:
	PYTHONPATH=src .venv/bin/python3 experiments/regret/run_regret.py \
		--n-train 5000 --n-eval 2000

lambda-sweep:
	PYTHONPATH=src .venv/bin/python3 experiments/churn_lambda/run_lambda_sweep.py \
		--n-eval 2000

horizon:
	PYTHONPATH=src .venv/bin/python3 experiments/horizon/run_horizon.py \
		--n-eval 2000 --eval-draws 3

dr-diagnosis:
	cd experiments/tier1_criteo && PYTHONPATH=../../src ../../.venv/bin/python3 \
		run_dr_diagnosis.py --draws 3

# Separate target rather than folding into `dr-diagnosis`: this sweeps
# n_folds in {2,5,10,20} across the same 3 disjoint blocks, which refits the
# cross-fitted outcome model dozens of extra times and takes far longer than
# the single-n_folds diagnosis above. Keeping it a separate target means
# `make dr-diagnosis` stays fast and its committed artifact is untouched by
# runs of this one.
dr-foldsweep:
	cd experiments/tier1_criteo && PYTHONPATH=../../src ../../.venv/bin/python3 \
		run_dr_diagnosis.py --draws 3 --fold-sweep

demo:
	PYTHONPATH=src .venv/bin/python3 -m recovery_ledger.cli

# Tier 2 batch experiment (spec section 11.1) — the B1 headline number.
# Trains an uplift model on randomised simulator data, then measures
# incremental rupees recovered vs a randomised no-contact holdout over a
# fresh eval batch. See experiments/tier2_simulation/REPORT.md.
eval:
	PYTHONPATH=src .venv/bin/python3 experiments/tier2_simulation/run_batch.py \
		--n-train 5000 --n-eval 2000

# 5-baseline comparison (spec section 11.3). See experiments/tier2_simulation/REPORT.md.
baselines:
	PYTHONPATH=src:experiments/tier2_simulation .venv/bin/python3 \
		experiments/tier2_simulation/run_baselines.py --n-train 5000 --n-eval 2000

# Negotiation showpiece: Section 43B(h) clock + NPV solver + kernel envelope
# + grounded LLM drafting (spec 9.4).
negotiate:
	PYTHONPATH=src .venv/bin/python3 experiments/negotiation/run_negotiation.py

# Contact-free recovery: fleet-level issuer degradation (spec 8.4, claim N6).
fleet:
	PYTHONPATH=src:experiments/tier2_simulation .venv/bin/python3 \
		experiments/fleet/run_fleet.py --n-train 5000 --n-eval 2000

# Reply-intent classification accuracy vs a hand-authored labelled set
# (spec section 8.5 requires this validation). Needs a local Ollama.
listener-eval:
	PYTHONPATH=src .venv/bin/python3 experiments/listener_eval/run_eval.py --set gold

# Browsable audit trail (bar requirement B4). Self-contained HTML — no npm, no
# build step, no network. Uses the rich batch ledger when `make eval` has been
# run, otherwise falls back to the demo ledger.
dashboard: frontend-build
	@if [ -f experiments/tier2_simulation/batch_ledger.json ]; then \
		PYTHONPATH=src .venv/bin/python3 dashboard/build_dashboard.py \
			--ledger experiments/tier2_simulation/batch_ledger.json --max-cases 80; \
	else \
		$(MAKE) demo >/dev/null && PYTHONPATH=src .venv/bin/python3 dashboard/build_dashboard.py; \
	fi
	@echo ""
	@echo "React app : dashboard/dist/index.html   (make dashboard-serve)"
	@echo "Fallback  : dashboard/index.html        (single file, opens directly)"

# Compiles the React + Vite front end into dashboard/dist. Skipped with a clear
# message if node is unavailable, so the Python-only path still works.
frontend-build:
	@if command -v npm >/dev/null 2>&1; then \
		[ -d frontend/node_modules ] || npm --prefix frontend install --silent; \
		npm --prefix frontend run build --silent; \
	else \
		echo "npm not found - skipping the React build, using the single-file fallback"; \
	fi

# The React build fetches data.json, which browsers block over file://, so it
# needs a static server rather than a double-click.
dashboard-serve:
	@.venv/bin/python3 dashboard/serve.py

frontend-dev:
	npm --prefix frontend run dev

# Does the rendered page actually say what the artifacts support? The build
# passing proves the page compiles, not that it says anything: a lookup
# regression once removed three headline figures from under the baselines
# chart with no error at all — TypeScript satisfied, build clean, section
# simply gone. Needs a server running (`make live` or `make dashboard-serve`).
verify-page:
	@.venv/bin/python3 dashboard/verify_page.py $${URL:-http://localhost:5175/}

# The live console: the same static dashboard, plus a backend that drives the
# real agent. Start a run and watch the loop write the ledger, engage the kill
# switch mid-run, fire the red-team suite at the compliance kernel one attack
# at a time (and switch rules off to prove they were doing the work), re-run a
# case with one fact of the world changed, or tamper with a ledger entry and
# watch verification catch it.
#
# Standard library only - nothing to install beyond `make setup`. --warm fits
# the uplift and churn models up front so the first run is not waiting on them.
live: dashboard
	PYTHONPATH=src .venv/bin/python3 -m recovery_ledger.live.server --warm

# Sensitivity sweep (spec section 7.3) — is the policy RANKING stable when the
# simulator's invented constants are swept across defensible ranges?
sensitivity:
	PYTHONPATH=src:experiments/tier2_simulation .venv/bin/python3 \
		experiments/sensitivity/run_sweep.py --n-train 3000 --n-eval 1500 --eval-draws 3

# Off-policy evaluation in the deployment loop: can a policy that was never
# run be valued from the logs of the one that was? Deploys the EV policy with
# epsilon-greedy exploration, estimates six candidate policies off-policy, and
# checks every estimate against the truth the simulator can be asked for.
# Replicated over independent logging draws, because coverage from a single
# log is a coin flip.
ope:
	PYTHONPATH=src .venv/bin/python3 experiments/ope_deployment/run_ope_deployment.py

# Disparity audit of the POLICY, as distinct from the kernel's audit of each
# action. Contact and work rates by language, B2B status, amount and loss
# type, conditioned on the two things the objective is entitled to use
# (predicted uplift and amount), with permutation tests and a Bonferroni
# correction across the sixteen hypotheses.
fairness:
	PYTHONPATH=src .venv/bin/python3 experiments/fairness/run_fairness.py

# Acting on a lower confidence bound instead of a point estimate. The
# disparity audit found the policy contacting cases whose true value of
# contact is negative, because tau_hat = 0.02 from a model that understands a
# segment and tau_hat = 0.02 from a model that is guessing produce the same
# decision. This sweeps `tau_hat - k * se` and measures what caution buys.
pessimism:
	PYTHONPATH=src .venv/bin/python3 experiments/pessimism/run_pessimism.py

# The statistic behind novelty claim N2, measured at a sample size where it
# converges. It was reported as 1.93x from a single n=5,000 draw, where the
# ratio ranges 0.72x-1.87x across seeds.
dnd-signal:
	PYTHONPATH=src .venv/bin/python3 experiments/dnd_signal/run_dnd_signal.py

# Adversarial suite against the compliance kernel (spec section 9.5).
# Named attacks + a hostile policy end to end + randomised fuzz.
redteam:
	PYTHONPATH=src:redteam .venv/bin/python3 redteam/run_redteam.py --fuzz-samples 5000
