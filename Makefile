.PHONY: setup test tier1-hillstrom tier1-criteo demo eval baselines sensitivity redteam dashboard listener-eval fleet negotiate frontend-build dashboard-serve frontend-dev live

setup:
	uv venv --python 3.12
	uv pip install -e ".[dev]"

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
		experiments/sensitivity/run_sweep.py --n-train 3000 --n-eval 1500

# Adversarial suite against the compliance kernel (spec section 9.5).
# Named attacks + a hostile policy end to end + randomised fuzz.
redteam:
	PYTHONPATH=src:redteam .venv/bin/python3 redteam/run_redteam.py --fuzz-samples 5000
