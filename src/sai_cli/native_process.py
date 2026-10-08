"""Bounded native reads under the caller's existing operating-system identity."""

from __future__ import annotations

import json
import selectors
import subprocess
import time
from typing import Any, Mapping, Sequence

from .errors import ContractError, UnavailableError


MAX_NATIVE_BYTES = 32 * 1024 * 1024


def read_native_json(argv: Sequence[str], *, environ: Mapping[str, str], timeout: float) -> dict[str, Any]:
    """Run one native client, without a shell, privilege change or HTTP fallback."""
    try:
        process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, env=dict(environ), bufsize=0)
    except FileNotFoundError as exc:
        raise UnavailableError("the native Slurm client is not installed or is not on PATH",
                               code="native_client_unavailable") from exc
    except OSError as exc:
        raise UnavailableError("the native client could not be started", code="native_query_failed") from exc

    output = bytearray()
    stderr_bytes = 0
    deadline = time.monotonic() + timeout
    try:
        with selectors.DefaultSelector() as selector:
            assert process.stdout is not None and process.stderr is not None
            selector.register(process.stdout, selectors.EVENT_READ, "stdout")
            selector.register(process.stderr, selectors.EVENT_READ, "stderr")
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise UnavailableError("the native query timed out", code="native_query_timeout")
                for key, _ in selector.select(remaining):
                    chunk = key.fileobj.read(65536)
                    if not chunk:
                        selector.unregister(key.fileobj)
                    elif key.data == "stdout":
                        output.extend(chunk)
                        if len(output) > MAX_NATIVE_BYTES:
                            raise UnavailableError("the native response is too large; narrow the query",
                                                   code="native_response_too_large")
                    else:
                        stderr_bytes += len(chunk)
                        if stderr_bytes > 65536:
                            raise UnavailableError("the native query produced excessive diagnostics",
                                                   code="native_query_failed")
            try:
                code = process.wait(timeout=max(0, deadline - time.monotonic()))
            except subprocess.TimeoutExpired as exc:
                raise UnavailableError("the native query timed out", code="native_query_timeout") from exc
        if code:
            raise UnavailableError("Slurm could not complete the query; check the native filters and site connection",
                                   code="native_query_failed")
    finally:
        if process.poll() is None:
            process.kill()
        process.wait()
        if process.stdout is not None:
            process.stdout.close()
        if process.stderr is not None:
            process.stderr.close()

    try:
        value = json.loads(output)
    except (ValueError, UnicodeError) as exc:
        raise ContractError("Slurm returned invalid JSON", code="native_response_invalid") from exc
    if not isinstance(value, dict):
        raise ContractError("Slurm returned an invalid response", code="native_response_invalid")
    return value
