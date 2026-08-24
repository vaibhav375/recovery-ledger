"""The live console's backend. Standard library only, on purpose.

`make dashboard` already produces a static audit trail that opens with no
server at all, and that path must keep working — it is the fallback when
anything here is unavailable. So this server adds capability without adding a
dependency: no FastAPI, no uvicorn, no websockets, nothing to install. A
judge with a clean checkout runs `make live` and it works.

It serves two things from one port:

* `dashboard/dist/` as static files, with `Cache-Control: no-store` — every
  Vite build produces new content-hashed asset names while `index.html` keeps
  its URL, so a cached index asks for assets that no longer exist and renders
  a blank page that looks exactly like a broken app.
* `/api/*`, including a Server-Sent Events stream of a real agent run.

SSE rather than websockets because the traffic is one-directional and SSE is
a text protocol `http.server` can speak without a library. Control actions
(start, kill) are ordinary POSTs.
"""

from __future__ import annotations

import argparse
import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from recovery_ledger.kernel.provenance import registry_json
from recovery_ledger.live import range as krange
from recovery_ledger.live.session import (
    DEFAULT_SEED,
    RunSession,
    build_kernel,
    new_session,
    run_session,
)

DIST = Path(__file__).resolve().parents[3] / "dashboard" / "dist"

# A run is capped so a stray request cannot pin a CPU for minutes. 500 cases
# at ~10 ms each is about five seconds of real agent time — long enough to be
# interrupted by hand when paced, short enough to never feel stuck.
MAX_CASES = 500
MAX_PACE_MS = 400

_RUNS: dict[str, RunSession] = {}
_RUNS_LOCK = threading.Lock()
# Only the most recent handful are kept; each holds a full ledger.
_MAX_RETAINED_RUNS = 8


def _remember(session: RunSession) -> None:
    with _RUNS_LOCK:
        _RUNS[session.run_id] = session
        while len(_RUNS) > _MAX_RETAINED_RUNS:
            oldest = next(iter(_RUNS))
            _RUNS.pop(oldest, None)


def _get_run(run_id: str) -> RunSession | None:
    with _RUNS_LOCK:
        return _RUNS.get(run_id)


class Handler(BaseHTTPRequestHandler):
    server_version = "RecoveryLedgerLive/1.0"

    # ---- plumbing ----
    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _json(self, payload: dict | list, status: int = 200) -> None:
        self._send(status, json.dumps(payload, default=str).encode(), "application/json")

    def _body(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length") or 0)
            if not length:
                return {}
            return json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError):
            return {}

    def log_message(self, fmt: str, *args) -> None:  # quieter console
        message = fmt % args
        if " 4" in message or " 5" in message:  # 4xx/5xx only
            super().log_message(fmt, *args)

    # ---- routing ----
    def do_GET(self) -> None:  # noqa: N802
        url = urlparse(self.path)
        route, query = url.path, parse_qs(url.query)

        if route == "/api/health":
            return self._json({
                "ok": True,
                "rules": [r.name for r in build_kernel().rules],
                "attacks": len(krange.attack_catalogue()),
                "levers": len(krange.lever_catalogue()),
                "dist_built": (DIST / "index.html").exists(),
            })
        if route == "/api/provenance":
            return self._json(registry_json())
        if route == "/api/attacks":
            return self._json({
                "attacks": krange.attack_catalogue(),
                "rules": krange.all_rule_names(),
            })
        if route == "/api/levers":
            return self._json({
                "levers": krange.lever_catalogue(),
                "seed": DEFAULT_SEED,
                "roster": krange.ROSTER_N,
            })
        if route == "/api/stream":
            return self._stream(query.get("run", [""])[0])
        return self._static(route)

    def do_POST(self) -> None:  # noqa: N802
        route = urlparse(self.path).path
        body = self._body()

        if route == "/api/run":
            seed = int(body.get("seed") or DEFAULT_SEED)
            n_cases = max(1, min(int(body.get("n_cases") or 25), MAX_CASES))
            pace_ms = max(0, min(int(body.get("pace_ms") or 0), MAX_PACE_MS))
            session = new_session(seed=seed, n_cases=n_cases, pace_ms=pace_ms)
            _remember(session)
            threading.Thread(
                target=run_session, args=(session,), daemon=True,
                name=f"run-{session.run_id}",
            ).start()
            return self._json({
                "run_id": session.run_id,
                "seed": seed,
                "n_cases": n_cases,
                "pace_ms": pace_ms,
            })

        if route == "/api/kill":
            session = _get_run(str(body.get("run_id") or ""))
            if session is None:
                return self._json({"error": "unknown run"}, status=404)
            # The real KillSwitch the agent loop checks — stopping rule 11.
            session.kill.engage()
            return self._json({"run_id": session.run_id, "engaged": True})

        if route == "/api/attack":
            name = str(body.get("name") or "")
            disabled = [str(r) for r in (body.get("disabled_rules") or [])]
            return self._json(krange.fire(name, disabled))

        if route == "/api/counterfactual":
            index = body.get("index")
            return self._json(krange.counterfactual(
                seed=int(body.get("seed") or DEFAULT_SEED),
                index=None if index in (None, "", "auto") else int(index),
                lever=str(body.get("lever") or ""),
            ))

        if route == "/api/verify":
            entries = body.get("entries")
            if not isinstance(entries, list):
                return self._json({"error": "expected {entries: [...]}"}, status=400)
            return self._json(krange.verify_entries(entries))

        return self._json({"error": f"no route {route}"}, status=404)

    # ---- SSE ----
    def _stream(self, run_id: str) -> None:
        session = _get_run(run_id)
        if session is None:
            return self._json({"error": "unknown run"}, status=404)

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "keep-alive")
        # Nginx and friends buffer SSE into uselessness without this.
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

        try:
            for event in session.stream():
                chunk = f"data: {json.dumps(event, default=str)}\n\n".encode()
                self.wfile.write(chunk)
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            # The browser navigated away mid-run. Not an error.
            pass

    # ---- static ----
    def _static(self, route: str) -> None:
        if not DIST.is_dir():
            return self._json(
                {"error": "dashboard/dist not built — run `make dashboard` first"},
                status=503,
            )
        rel = route.lstrip("/") or "index.html"
        target = (DIST / rel).resolve()
        # Path traversal guard: everything served must live under dist/.
        if not str(target).startswith(str(DIST.resolve())):
            return self._json({"error": "forbidden"}, status=403)
        if target.is_dir():
            target = target / "index.html"
        if not target.is_file():
            # Single-page app: unknown paths fall back to index.html.
            target = DIST / "index.html"
            if not target.is_file():
                return self._json({"error": "not found"}, status=404)

        types = {
            ".html": "text/html; charset=utf-8",
            ".js": "text/javascript; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".json": "application/json",
            ".svg": "image/svg+xml",
            ".woff2": "font/woff2",
            ".png": "image/png",
        }
        self._send(200, target.read_bytes(), types.get(target.suffix, "application/octet-stream"))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", type=int, default=5175)
    ap.add_argument("--no-open", action="store_true")
    ap.add_argument(
        "--warm", action="store_true",
        help="fit the uplift and churn models at startup instead of on the first run",
    )
    args = ap.parse_args()

    if args.warm:
        from recovery_ledger.live.session import get_models

        print("fitting models …", end=" ", flush=True)
        models = get_models()
        print(f"done in {models.train_seconds:.1f}s "
              f"(corr(tau_hat, tau_true) = {models.uplift_correlation:.2f})")

    server = ThreadingHTTPServer(("", args.port), Handler)
    server.daemon_threads = True
    url = f"http://localhost:{args.port}/"
    print(f"Recovery Ledger — live console → {url}")
    if not (DIST / "index.html").exists():
        print("  ! dashboard/dist is not built. Run `make dashboard` for the UI;")
        print("    the /api routes work regardless.")
    print("  Ctrl+C to stop")
    if not args.no_open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
