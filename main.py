#!/usr/bin/env python3
"""Launch both assignment dashboards and serve the landing page."""

from __future__ import annotations

import argparse
from functools import partial
import os
import subprocess
import sys
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parent


class AssignmentHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


class AssignmentRequestHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, scivis_url: str, **kwargs):
        self.scivis_url = scivis_url
        super().__init__(*args, **kwargs)

    def do_GET(self) -> None:
        if self.path.rstrip("/") == "/task1":
            self.send_response(302)
            self.send_header("Location", self.scivis_url)
            self.end_headers()
            return
        if self.path in ("/", "/index.html"):
            page = (ROOT / "index.html").read_text(encoding="utf-8")
            page = page.replace("__SCIVIS_URL__", self.scivis_url)
            body = page.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()


def wait_for_scivis(url: str, process: subprocess.Popen, timeout: float = 90) -> None:
    """Wait until Streamlit responds, or fail with a useful startup message."""
    deadline = time.monotonic() + timeout
    health_url = url.rstrip("/") + "/_stcore/health"
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(
                "The SciVis Streamlit process exited during startup. "
                "Check that dependencies are installed and the prepared gridMET file exists."
            )
        try:
            with urlopen(health_url, timeout=1) as response:
                if response.status == 200:
                    return
        except (OSError, URLError):
            time.sleep(0.4)
    raise TimeoutError("SciVis did not become ready within 90 seconds.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1", help="Local interface to bind (default: 127.0.0.1)")
    parser.add_argument("--landing-port", type=int, default=8000, help="Landing page and InfoVis port")
    parser.add_argument("--scivis-port", type=int, default=8501, help="SciVis Streamlit port")
    args = parser.parse_args()

    scivis_url = f"http://{args.host}:{args.scivis_port}"
    landing_url = f"http://{args.host}:{args.landing_port}/"
    command = [
        sys.executable, "-m", "streamlit", "run", "app.py",
        "--server.address", args.host,
        "--server.port", str(args.scivis_port),
        "--server.headless", "true",
    ]
    process = subprocess.Popen(command, cwd=ROOT / "task1", env=os.environ.copy())
    server = None
    try:
        print("Starting SciVis dashboard…", flush=True)
        wait_for_scivis(scivis_url, process)
        handler = partial(
            AssignmentRequestHandler,
            directory=str(ROOT),
            scivis_url=scivis_url,
        )
        server = AssignmentHTTPServer((args.host, args.landing_port), handler)
        print("Both dashboards are ready:", flush=True)
        print(f"  Assignment home: {landing_url}", flush=True)
        print(f"  SciVis direct:   {scivis_url}", flush=True)
        print("Press Ctrl+C to stop both dashboards.", flush=True)
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping dashboards…", flush=True)
    except (OSError, RuntimeError, TimeoutError) as error:
        print(f"Could not start the assignment dashboards: {error}", file=sys.stderr, flush=True)
        return 1
    finally:
        if server is not None:
            server.server_close()
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
