"""App-owned loopback backend; stdin EOF ends this one family process."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import signal
import sys
import threading

import server


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--experimental-default", action="store_true")
    args = parser.parse_args()
    server.configure_data_dir(args.data_dir.resolve())
    server.configure_experimental_cross_generation(args.experimental_default)
    # In the App, backend and static are sibling resource directories.
    bundled_static = Path(__file__).resolve().parent.parent / "static"
    if bundled_static.is_dir():
        server.STATIC_DIR = bundled_static
    server.read_workspace()
    httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.FamilyHandler)
    stopping = threading.Event()

    def stop() -> None:
        if not stopping.is_set():
            stopping.set()
            httpd.shutdown()

    def watch_parent() -> None:
        for _ in sys.stdin:
            pass
        stop()

    def signal_stop(_signum, _frame) -> None:
        threading.Thread(target=stop, daemon=True).start()

    signal.signal(signal.SIGTERM, signal_stop)
    # Start serve_forever before the stdin watcher: shutdown otherwise deadlocks.
    serving = threading.Thread(target=httpd.serve_forever, name="genea-http")
    serving.start()
    port = httpd.server_address[1]
    print(json.dumps({"status": "ready", "port": port, "url": f"http://127.0.0.1:{port}"}), flush=True)
    sys.stdout = sys.stderr
    threading.Thread(target=watch_parent, name="genea-parent", daemon=True).start()
    try:
        serving.join()
    except KeyboardInterrupt:
        stop()
        serving.join()
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
