"""Entry point for the Hugging Face Space.

The Docker SDK is a paid feature, so this Space uses the Gradio SDK. That SDK
does not require a Gradio app: it installs requirements.txt, runs this file,
and serves whatever is listening on port 7860. What listens here is the same
console server that runs on a laptop, unchanged — the live section needs a
process that holds a run in memory and streams events while the agent loop
executes, and that is all this provides.

--warm fits the uplift and churn models before the port opens, so the cost is
paid once when the Space starts rather than on the first visitor's click.
"""
from __future__ import annotations

import os
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "src"))

# The Space proxies 7860. Keeping it in the environment rather than as a flag
# means the server's own default applies everywhere else.
os.environ.setdefault("PORT", "7860")

from recovery_ledger.live.server import main  # noqa: E402

if __name__ == "__main__":
    sys.argv = [sys.argv[0], "--warm", "--no-open"]
    main()
