# The live console, as a container.
#
# This exists because the console cannot be static. Everything above it on the
# page is measurement from runs that already happened and needs no server; the
# console drives the agent in real time. It holds a run in memory, streams
# events over SSE while the loop executes, and lets you engage the real kill
# switch mid-run. That needs one process with shared memory and a long-lived
# connection, which is why it is a container and not a function.

FROM python:3.12-slim

# A non-root user, because the container has no business running as root and
# Hugging Face Spaces expects a writable home for the user it runs as.
RUN useradd -m -u 1000 app
WORKDIR /app

# Dependencies first, so editing the code does not re-resolve the wheel tree.
COPY --chown=app:app requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=app:app src/ ./src/
COPY --chown=app:app dashboard/ ./dashboard/
# The attack suite lives outside the package on purpose: the interactive range
# and the reported block rate load the same definitions, so they cannot drift.
# api/range.py finds it by adding this directory to sys.path.
COPY --chown=app:app redteam/ ./redteam/

USER app
ENV PYTHONPATH=/app/src \
    PYTHONUNBUFFERED=1 \
    PORT=7860

EXPOSE 7860

# --warm fits the uplift and churn models at startup. It takes a few seconds
# and it happens once per container rather than on the first visitor's click,
# so the console feels like the agent rather than like the training.
CMD ["python", "-m", "recovery_ledger.live.server", "--warm", "--no-open"]
