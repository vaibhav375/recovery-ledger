# The live console, built from this repository.
#
# The dashboard above the console is a static report and is happily served by
# GitHub Pages. The console is not: it holds a run in memory, streams events
# over SSE while the agent loop executes, and lets you engage the real kill
# switch mid-run. That needs one process with shared memory and a long-lived
# connection, so it ships as a container.
#
# Two stages because the front end is TypeScript and the server is Python, and
# there is no reason for node to be in the image that runs.

# ---- stage 1: compile the front end -------------------------------------
FROM node:20-slim AS ui
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./frontend/
RUN npm --prefix frontend ci --silent
COPY frontend/ ./frontend/
# Vite writes to ../dashboard/dist, so the directory has to exist first.
RUN mkdir -p dashboard/dist && npm --prefix frontend run build --silent

# ---- stage 2: the server -------------------------------------------------
FROM python:3.12-slim

# Only what the live path touches. The research pipeline needs pyarrow,
# matplotlib, scikit-uplift, click and rich; the console does not, which was
# verified by blocking each import and running a session. Leaving them out
# takes roughly 180 MB off the image. econml is not optional: the uplift model
# the agent scores cases with is an econml T-learner.
RUN pip install --no-cache-dir \
      "numpy>=1.26" "pandas>=2.2" "scikit-learn>=1.4" "econml>=0.15" "pydantic>=2.6"

RUN useradd -m -u 1000 app
WORKDIR /app

COPY --chown=app:app src/ ./src/
# The attack suite lives outside the package on purpose: the interactive range
# and the reported block rate load the same definitions, so they cannot drift.
# live/range.py finds it by adding this directory to sys.path.
COPY --chown=app:app redteam/attacks.py ./redteam/
COPY --chown=app:app dashboard/build_dashboard.py ./dashboard/
COPY --chown=app:app --from=ui /build/dashboard/dist ./dashboard/dist

# Every headline number on the dashboard comes from these: the holdout, the
# baselines, the calibration checks, the fairness and fleet runs. The ledger
# below supplies only the case-by-case explorer. Without them the page renders
# with the structure intact and every value null, which reads as a broken build
# rather than a missing input — so they are copied explicitly, by name, and a
# missing one fails the build instead of the page.
COPY --chown=app:app claims.json ./
COPY --chown=app:app experiments/ ./experiments/
RUN test -s experiments/tier2_simulation/results.json \
    && test -s experiments/uplift_calibration/results_uplift_calibration.json \
    && test -s claims.json

# The ledger is a generated artifact, not a committed one — running the demo
# produces it in a few seconds, and generating it here means the image cannot
# ship a dashboard that disagrees with the code that made it. data.json, which
# is the entire content of the page, is then built from that ledger.
RUN PYTHONPATH=/app/src python -m recovery_ledger.cli --out /tmp/demo_ledger.json \
    && PYTHONPATH=/app/src python dashboard/build_dashboard.py \
         --ledger /tmp/demo_ledger.json --out /tmp/fallback.html \
    && rm -f /tmp/fallback.html /tmp/demo_ledger.json \
    && chown -R app:app /app/dashboard

USER app
ENV PYTHONPATH=/app/src \
    PYTHONUNBUFFERED=1 \
    PORT=10000

EXPOSE 10000

# --warm fits the models before the port opens. On a host that sleeps, a
# visitor is already waiting for the container; making them wait for the models
# too, on the first click, is worse than folding it into the same wait.
CMD ["python", "-m", "recovery_ledger.live.server", "--warm", "--no-open"]
