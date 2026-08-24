"""Static server for the compiled dashboard.

Exists instead of a bare `python -m http.server` for one reason: every Vite
build produces new content-hashed asset filenames, but `index.html` keeps the
same URL. A browser that has cached the old `index.html` will keep asking for
asset hashes that no longer exist, get 404s, and render a blank page — which
looks exactly like the app being broken.

Sending no-store on every response makes a plain reload always correct.
"""

from __future__ import annotations

import argparse
import functools
import http.server
import socketserver
import webbrowser
from pathlib import Path

DIST = Path(__file__).parent / "dist"


class NoCacheHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

    def log_message(self, fmt: str, *args) -> None:  # quieter console
        if "404" in (fmt % args):
            super().log_message(fmt, *args)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", type=int, default=5174)
    ap.add_argument("--no-open", action="store_true")
    args = ap.parse_args()

    if not (DIST / "index.html").exists():
        raise SystemExit(
            f"{DIST}/index.html not found — run `make dashboard` first "
            f"(it compiles the front end and writes data.json)."
        )

    handler = functools.partial(NoCacheHandler, directory=str(DIST))
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", args.port), handler) as httpd:
        url = f"http://localhost:{args.port}/"
        print(f"Recovery Ledger dashboard → {url}")
        print("Cache-Control: no-store (a plain reload always gets the current build)")
        print("Ctrl+C to stop")
        if not args.no_open:
            webbrowser.open(url)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nstopped")


if __name__ == "__main__":
    main()
