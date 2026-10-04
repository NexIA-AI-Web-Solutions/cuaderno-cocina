"""Keep nginx and gunicorn alive together, with bounded graceful shutdown."""
from __future__ import annotations

import signal
import subprocess
import sys
import time


def supervise(commands: list[list[str]], *, grace_seconds=30.0) -> int:
    children = []
    stopping = False

    def stop(_signal, _frame):
        nonlocal stopping
        stopping = True

    previous = {number: signal.signal(number, stop) for number in (signal.SIGTERM, signal.SIGINT)}
    try:
        for command in commands:
            children.append(subprocess.Popen(command))
        while not stopping:
            for child in children:
                status = child.poll()
                if status is not None:
                    # Even a clean unexpected daemon exit is a failed container.
                    return status if status > 0 else 128 - status if status < 0 else 1
            time.sleep(0.1)
        return 0
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
        deadline = time.monotonic() + grace_seconds
        for child in children:
            try:
                child.wait(timeout=max(0.01, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
        for number, handler in previous.items():
            signal.signal(number, handler)


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] != "gunicorn":
        raise ValueError("The application command must be gunicorn.")
    return supervise([["nginx", "-g", "daemon off; pid /tmp/nginx.pid;"], sys.argv[1:]])


if __name__ == "__main__":
    raise SystemExit(main())
