#!/usr/bin/env python

import os
import signal
import subprocess
import sys
import time

worker: subprocess.Popen | None = None


def log(message: str) -> None:
    """Unbuffered, so lines appear in Render's log stream immediately."""
    print(f"[start] {message}", flush=True)


def shutdown(signum: int, _frame: object) -> None:
    """Pass termination on to the worker so it can finish cleanly."""
    log(f"received signal {signum}, stopping worker")
    if worker and worker.poll() is None:
        worker.terminate()
        try:
            worker.wait(timeout=10)
        except subprocess.TimeoutExpired:
            worker.kill()
    sys.exit(0)


def main() -> int:
    global worker

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    # ---------------- 1. migrations ----------------
    log("applying database migrations")
    result = subprocess.run(["alembic", "upgrade", "head"], check=False)
    if result.returncode != 0:
        # Starting the API against a stale schema produces confusing 500s
        # later. Fail loudly here instead.
        log(f"migrations FAILED (exit {result.returncode}) - refusing to start")
        return result.returncode
    log("migrations applied")

    # ---------------- 2. background worker ----------------
    log("starting arq worker")
    worker = subprocess.Popen(["arq", "app.workers.main.WorkerSettings"])

    # Give it a moment, then confirm it survived startup. A worker that dies
    # immediately (almost always a bad REDIS_URL) would otherwise leave the
    # API cheerfully accepting jobs that never process - the hardest failure
    # mode to diagnose later.
    time.sleep(3)
    if worker.poll() is not None:
        log(f"worker exited immediately (code {worker.returncode})")
        log("check REDIS_URL - jobs will stay queued without a worker")
        return 1
    log(f"worker running (pid {worker.pid})")

    # ---------------- 3. API in the foreground ----------------
    port = os.environ.get("PORT", "8000")
    log(f"starting API on port {port}")

    api = subprocess.Popen([
        "uvicorn", "app.main:app",
        "--host", "0.0.0.0",
        "--port", str(port),
    ])

    # Whichever process exits first takes the container down, so Render
    # restarts everything. Serving an API whose jobs silently never process is
    # worse than being down.
    while True:
        if api.poll() is not None:
            log(f"API exited (code {api.returncode})")
            if worker.poll() is None:
                worker.terminate()
            return api.returncode or 0

        if worker.poll() is not None:
            log(f"worker exited (code {worker.returncode}) - stopping API")
            api.terminate()
            api.wait(timeout=10)
            return worker.returncode or 1

        time.sleep(2)


if __name__ == "__main__":
    sys.exit(main())
