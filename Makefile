.PHONY: setup test tier1-hillstrom tier1-criteo demo eval redteam

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
		--n-train 1000 --n-eval 1000

# Not yet implemented — see README.md Status section.
redteam:
	@echo "make redteam: not yet implemented"; exit 1
