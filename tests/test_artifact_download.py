from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import StringIO
import json
import threading
import time

import pytest

from sai_cli.artifact_download import ArtifactDownloadGrant, DOWNLOAD_PATH, RANGE_BYTES
from sai_cli.cli import main
from sai_cli.client import PortalClient
from sai_cli.errors import ContractError
from test_cli_integration import _env
from test_site_transport import http_endpoint


ARTIFACT = "artifact-" + "a" * 40
VERSION = "b" * 64
SCOPE = {"workspace_key": "project:project-example", "site_id": "site-a",
         "run_ref": "run-example-1", "artifact_ref": ARTIFACT}


def grant(origin, size, **changes):
    return {"schema_version": "compute.run-artifact-download/v1", **SCOPE,
            "download_name": "result data.bin", "size_bytes": size, "version": VERSION,
            "download_url": origin + DOWNLOAD_PATH, "capability": "synthetic-file-capability",
            "expires_at": int(time.time()) + 30, "transfer_until": int(time.time()) + 300,
            "range_max_bytes": RANGE_BYTES, **changes}


@contextmanager
def binary_endpoint(respond):
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            call = {"path": self.path, "range": self.headers.get("Range"),
                    "etag": self.headers.get("If-Match"), "bearer": self.headers.get("Authorization"),
                    "capability": self.headers.get("X-SAI-Capability")}
            calls.append(call)
            status, headers, data = respond(call, len(calls))
            self.send_response(status)
            for name, value in headers.items():
                self.send_header(name, str(value))
            self.end_headers()
            try:
                self.wfile.write(data)
            except (ConnectionError, BrokenPipeError):
                pass

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", calls
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def response(data, call):
    if not data:
        return 200, {"Content-Length": "0", "ETag": f'"{VERSION}"'}, b""
    start, end = map(int, call["range"].removeprefix("bytes=").split("-"))
    content = data[start:end + 1]
    return 206, {"Content-Length": len(content), "ETag": f'"{VERSION}"',
                 "Content-Range": f"bytes {start}-{end}/{len(data)}"}, content


def invoke(tmp_path, origin, *, before=False, destination=None):
    out, err = StringIO(), StringIO()
    command = ["runs", "download", SCOPE["run_ref"], "--workspace-key", SCOPE["workspace_key"],
               "--artifact-ref", ARTIFACT, "--artifact-cursor", "100", "--output",
               str(destination or tmp_path / "result data.bin")]
    connection = ["--site", "site-a", "--base-url", origin, "--timeout", "2"]
    code = main(connection + command if before else command + connection,
                environ=_env(tmp_path), stdout=out, stderr=err)
    return code, out.getvalue(), err.getvalue()


@pytest.mark.parametrize("before", [False, True])
@pytest.mark.parametrize("empty", [False, True])
def test_real_http_download_is_exact_private_binary_and_keeps_identity_at_center(tmp_path, before, empty):
    content = b"" if empty else bytes(range(256)) * (RANGE_BYTES // 256 + 1)
    with binary_endpoint(lambda call, _: response(content, call)) as (site, reads):
        with http_endpoint(lambda *_: (200, grant(site, len(content)))) as (center, issued):
            code, out, err = invoke(tmp_path, center, before=before)
    assert code == 0 and err == ""
    destination = tmp_path / "result data.bin"
    assert destination.read_bytes() == content and destination.stat().st_mode & 0o777 == 0o600
    receipt = json.loads(out)
    assert receipt == {"schema_version": "compute.run-artifact-saved/v1", **SCOPE,
                       "output": str(destination), "size_bytes": len(content), "version": VERSION}
    assert len(issued) == 1 and issued[0]["method"] == "POST"
    assert issued[0]["path"] == f"/v1/compute/cli/runs/run-example-1/artifacts/{ARTIFACT}/download"
    assert issued[0]["body"] == {"workspace_key": SCOPE["workspace_key"], "site_id": "site-a",
                                  "artifact_cursor": "100", "version": None}
    assert issued[0]["bearer"] == "Bearer test-bearer-token" and issued[0]["capability"] is None
    assert len(reads) == (1 if empty else 2)
    assert all(row["bearer"] is None and row["capability"] == "synthetic-file-capability"
               and row["etag"] == f'"{VERSION}"' and row["path"] == DOWNLOAD_PATH for row in reads)
    assert not list(tmp_path.glob(".sai-download-*"))
    assert "capability" not in out and "test-bearer-token" not in out


@pytest.mark.parametrize("change", [None, "version", "size_bytes"])
def test_expired_capability_reissues_for_same_version_and_refuses_changed_file(tmp_path, change):
    content = b"first" * (RANGE_BYTES // 5 + 1)

    def site_reply(call, count):
        if count == 2:
            return 401, {"Content-Length": 0}, b""
        return response(content, call)

    with binary_endpoint(site_reply) as (site, reads):
        def issue(_call, count):
            changes = {change: "c" * 64 if change == "version" else len(content) + 1} if change and count == 2 else {}
            return 200, grant(site, len(content), capability=f"cap-{count}", **changes)
        with http_endpoint(issue) as (center, issued):
            code, out, _err = invoke(tmp_path, center)
    assert len(issued) == 2 and issued[1]["body"]["version"] == VERSION
    assert reads[1]["range"].startswith(f"bytes={RANGE_BYTES}-")
    if change:
        assert code == 7 and out == "" and not (tmp_path / "result data.bin").exists()
        assert len(reads) == 2
    else:
        assert code == 0 and (tmp_path / "result data.bin").read_bytes() == content
        assert reads[2]["range"] == reads[1]["range"] and reads[2]["capability"] == "cap-2"
    assert not list(tmp_path.glob(".sai-download-*"))


@pytest.mark.parametrize("failure", ["redirect", "etag", "range", "length", "encoding", "status", "interrupted", "denied"])
def test_invalid_binary_response_never_publishes_or_leaks_provider_text(tmp_path, failure):
    def reply(call, _count):
        status, headers, content = response(b"binary\x00data", call)
        if failure == "redirect":
            return 302, {"Location": "/credential-destination", "Content-Length": 0}, b""
        if failure == "etag": headers["ETag"] = '"another-version"'
        if failure == "range": headers["Content-Range"] = "bytes 1-11/12"
        if failure == "length": headers["Content-Length"] += 1
        if failure == "encoding": headers["Content-Encoding"] = "gzip"
        if failure == "status": status = 200
        if failure == "interrupted": content = content[:1]
        if failure == "denied": return 403, {"Content-Length": 21}, b"synthetic-secret-data"
        return status, headers, content
    with binary_endpoint(reply) as (site, reads), http_endpoint(lambda *_: (200, grant(site, 11))) as (center, _):
        code, out, err = invoke(tmp_path, center)
    assert code != 0 and out == "" and "synthetic-secret-data" not in err
    assert len(reads) == 1 and not (tmp_path / "result data.bin").exists()
    assert not list(tmp_path.glob(".sai-download-*"))


@pytest.mark.parametrize("kind", ["file", "symlink", "directory", "race"])
def test_existing_and_racing_output_paths_are_not_overwritten(tmp_path, kind):
    destination = tmp_path / "result data.bin"
    other = tmp_path / "original"; other.write_bytes(b"keep")
    if kind == "file": destination.write_bytes(b"keep")
    elif kind == "symlink": destination.symlink_to(other)
    elif kind == "directory": destination.mkdir()

    def reply(call, _count):
        if kind == "race": destination.symlink_to(other)
        return response(b"new", call)

    with binary_endpoint(reply) as (site, _), http_endpoint(lambda *_: (200, grant(site, 3))) as (center, issued):
        code, out, _ = invoke(tmp_path, center)
    assert code == 2 and out == "" and other.read_bytes() == b"keep"
    if kind != "race": assert issued == []
    if kind == "file": assert destination.read_bytes() == b"keep"
    if kind in {"symlink", "race"}: assert destination.is_symlink()
    assert not list(tmp_path.glob(".sai-download-*"))


def test_keyboard_interrupt_after_http_read_cleans_partial(tmp_path, monkeypatch):
    def interrupted(*_args):
        raise KeyboardInterrupt
    monkeypatch.setattr("sai_cli.artifact_download.os.write", interrupted)
    with binary_endpoint(lambda call, _: response(b"data", call)) as (site, reads):
        with http_endpoint(lambda *_: (200, grant(site, 4))) as (center, _):
            code, out, _ = invoke(tmp_path, center)
    assert code == 130 and out == "" and len(reads) == 1
    assert not (tmp_path / "result data.bin").exists() and not list(tmp_path.glob(".sai-download-*"))


def test_cancel_callback_after_binary_read_uses_private_directory_and_cleans_it(tmp_path, monkeypatch):
    stopped = []
    original = PortalClient.download_managed_run_artifact

    def cancellable(self, *args, **kwargs):
        return original(self, *args, **kwargs, cancelled=lambda: bool(stopped))

    def reply(call, _count):
        temporary, = tmp_path.glob(".sai-download-*")
        assert temporary.is_dir() and temporary.stat().st_mode & 0o777 == 0o700
        assert (temporary / "content.part").stat().st_mode & 0o777 == 0o600
        stopped.append(True)
        return response(b"data", call)

    monkeypatch.setattr(PortalClient, "download_managed_run_artifact", cancellable)
    with binary_endpoint(reply) as (site, _), http_endpoint(lambda *_: (200, grant(site, 4))) as (center, _):
        code, out, err = invoke(tmp_path, center)
    assert code == 130 and out == "" and "download_cancelled" in err
    assert not (tmp_path / "result data.bin").exists() and not list(tmp_path.glob(".sai-download-*"))


def test_cleanup_failure_preserves_original_http_error(tmp_path, monkeypatch):
    import os
    native = os.rmdir

    def denied(*_args, **_kwargs):
        raise PermissionError("synthetic cleanup failure")

    with binary_endpoint(lambda *_: (403, {"Content-Length": 0}, b"")) as (site, _):
        with http_endpoint(lambda *_: (200, grant(site, 4))) as (center, _):
            with monkeypatch.context() as context:
                context.setattr("sai_cli.artifact_download.os.rmdir", denied)
                code, out, err = invoke(tmp_path, center)
    assert code == 4 and out == "" and "http_403" in err and "cleanup" not in err
    temporary, = tmp_path.glob(".sai-download-*")
    assert list(temporary.iterdir()) == []
    native(temporary)


@pytest.mark.parametrize("changes", [
    {"size_bytes": True}, {"size_bytes": 2**53}, {"range_max_bytes": 1},
    {"site_id": "other-site"}, {"version": "bad"}, {"download_name": "../outside"},
    {"capability": "bad\nheader"}, {"capability": "a" * 16385},
    {"expires_at": 1}, {"download_url": "http://files.example.org" + DOWNLOAD_PATH},
    {"expires_at": int(time.time()) + 400}, {"transfer_until": int(time.time()) + 4000},
    {"download_url": "https://files.example.org/other"},
    {"download_url": "https://files.example.org" + DOWNLOAD_PATH + "?"},
    {"download_url": "https://files.example.org" + DOWNLOAD_PATH + "#"},
    {"download_url": "https://files.\x85example.org" + DOWNLOAD_PATH},
    {"download_url": "https://files.example.org" + DOWNLOAD_PATH + "?token=forbidden"},
    {"download_url": "https://user@files.example.org" + DOWNLOAD_PATH},
])
def test_invalid_grant_fails_closed(changes):
    with pytest.raises(ContractError):
        ArtifactDownloadGrant.from_payload(grant("https://files.example.org", 4, **changes), **SCOPE)


def test_grant_repr_never_contains_capability_or_origin():
    value = ArtifactDownloadGrant.from_payload(grant("https://files.example.org", 4), **SCOPE)
    assert "synthetic-file-capability" not in repr(value) and "files.example.org" not in repr(value)
