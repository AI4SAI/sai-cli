"""Finish an in-flight credential exchange before honoring terminal cancellation."""
from contextlib import contextmanager
import signal
import threading


def refresh_cancel_grace(timeout_seconds: float) -> float:
    # Discovery and token exchange each use the configured HTTP timeout.
    return 2 * timeout_seconds + 5


@contextmanager
def finish_credential_update():
    """Defer ordinary CLI interrupts; SIGKILL and lost responses are not recoverable."""
    if threading.current_thread() is not threading.main_thread():
        yield
        return
    pending = []

    def postpone(signum, frame):
        if not pending:
            pending.append(signum)

    previous = {kind: signal.signal(kind, postpone) for kind in (signal.SIGINT, signal.SIGTERM)}
    try:
        yield
    finally:
        for kind, handler in previous.items():
            signal.signal(kind, handler)
        if pending:
            # Cancellation must stop the caller before another read or business write.
            raise SystemExit(128 + pending[0])
