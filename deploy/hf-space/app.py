"""Entry point for the Hugging Face Space.

The Docker SDK is a paid feature, so this runs under the free Gradio SDK. That
SDK does not require a Gradio app: it installs requirements.txt, runs this
file, and serves whatever is listening on the Space's port. What listens is the
same console server that runs on a laptop, unchanged — the live section needs a
process that holds a run in memory and streams events while the agent loop
executes, and that is all this provides.

Two things here exist because of how a Space is supervised.

The port is taken from the environment rather than defaulted into it. A Space
tells the app where to listen and the supervisor watches that port; binding
somewhere else looks identical to a crash.

And the models are fitted in the background, after the port is open. Importing
the package costs about nine seconds on its own and cannot be avoided; adding
the fit on top of that, before binding, makes a supervisor wait longer than it
needs to for something it cannot distinguish from a crash.
"""
from __future__ import annotations

import os
import pathlib
import sys
import threading

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "src"))

PORT = int(os.environ.get("GRADIO_SERVER_PORT") or os.environ.get("PORT") or 7860)

from http.server import ThreadingHTTPServer  # noqa: E402

from recovery_ledger.live.server import Handler  # noqa: E402


def warm() -> None:
    """Fit the uplift and churn models off the critical path."""
    try:
        from recovery_ledger.live.session import get_models

        models = get_models()
        print(f"models fitted in {models.train_seconds:.1f}s "
              f"(corr(tau_hat, tau_true) = {models.uplift_correlation:.2f})",
              flush=True)
    except Exception as exc:  # noqa: BLE001 - a warm failure must not kill the port
        print(f"warm-up failed, models will fit on first use: {exc!r}", flush=True)


# Deliberately not behind `if __name__ == "__main__"`. A Space may import this
# module rather than execute it, and under an import guard nothing would ever
# bind — which the supervisor cannot tell apart from a crash. Serving at module
# level works either way.
server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
server.daemon_threads = True
print(f"Recovery Ledger — live console listening on 0.0.0.0:{PORT}", flush=True)
threading.Thread(target=warm, name="warm", daemon=True).start()
server.serve_forever()
