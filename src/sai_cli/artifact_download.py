"""Version-bound binary download and atomic, non-overwriting local publication."""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
import os
from pathlib import Path
import secrets
import sys
import time
from urllib.parse import urlsplit

from .artifact_content import VERSION
from .errors import AuthenticationError, ConfigError, ContractError, SaiCliError
from .transport import JsonTransport, normalize_base_url


DOWNLOAD_PATH = "/v1/site-files/artifacts/download"
RANGE_BYTES = 8 * 1024 * 1024
MAX_SIZE = 2**53 - 1


@dataclass(frozen=True)
class ArtifactDownloadGrant:
    download_name: str
    size_bytes: int
    version: str
    download_url: str = field(repr=False)
    capability: str = field(repr=False)
    expires_at: int
    transfer_until: int

    @classmethod
    def from_payload(cls, payload: object, *, workspace_key: str, site_id: str,
                     run_ref: str, artifact_ref: str, version: str | None = None) -> ArtifactDownloadGrant:
        if not isinstance(payload, Mapping) or any(payload.get(key) != value for key, value in {
            "schema_version": "compute.run-artifact-download/v1", "workspace_key": workspace_key,
            "site_id": site_id, "run_ref": run_ref, "artifact_ref": artifact_ref,
        }.items()):
            raise ContractError("the download grant does not match the requested file")
        name, size, current, url, capability, expiry, deadline = (
            payload.get(key) for key in ("download_name", "size_bytes", "version", "download_url",
                                         "capability", "expires_at", "transfer_until"))
        try:
            name_size = len(name.encode("utf-8")) if isinstance(name, str) else 0
        except UnicodeError as exc:
            raise ContractError("the download name is invalid") from exc
        now = time.time()
        if (not isinstance(name, str) or not 1 <= name_size <= 1024
                or name in {".", ".."} or "/" in name or "\\" in name
                or any(ord(c) < 32 or ord(c) == 127 for c in name)
                or type(size) is not int or not 0 <= size <= MAX_SIZE
                or not isinstance(current, str) or VERSION.fullmatch(current) is None
                or version is not None and current != version
                or not isinstance(capability, str) or not 1 <= len(capability) <= 16 * 1024
                or any(not 33 <= ord(c) <= 126 for c in capability)
                or type(expiry) is not int or type(deadline) is not int
                or not now < expiry <= min(deadline, now + 360) or deadline > now + 3660
                or type(payload.get("range_max_bytes")) is not int or payload["range_max_bytes"] != RANGE_BYTES):
            raise ContractError("the download grant is invalid or expired")
        try:
            if (not isinstance(url, str) or len(url) > 2048 or "?" in url or "#" in url
                    or any(ord(c) <= 32 or 127 <= ord(c) <= 159 for c in url)):
                raise ValueError
            parsed = urlsplit(url)
            if (parsed.path != DOWNLOAD_PATH or parsed.query or parsed.fragment or parsed.username is not None
                    or parsed.password is not None or parsed.port == 0 or "\\" in url):
                raise ValueError
            normalize_base_url(url, allow_insecure_http=False)
        except (ValueError, ConfigError) as exc:
            raise ContractError("the download origin is invalid") from exc
        return cls(name, size, current, url, capability, expiry, deadline)


def _read_range(grant: ArtifactDownloadGrant, offset: int, *, timeout_seconds: float) -> bytes:
    origin = grant.download_url[:-len(DOWNLOAD_PATH)]
    transport = JsonTransport(base_url=origin, timeout_seconds=timeout_seconds)
    count = min(RANGE_BYTES, grant.size_bytes - offset)
    headers = {"X-SAI-Capability": grant.capability, "If-Match": f'"{grant.version}"'}
    if count:
        headers["Range"] = f"bytes={offset}-{offset + count - 1}"
    response = transport.request_bytes(DOWNLOAD_PATH, headers=headers, maximum=count)
    received = {key.lower(): value for key, value in response.headers.items()}
    expected_range = f"bytes {offset}-{offset + count - 1}/{grant.size_bytes}" if count else None
    if (response.status != (206 if count else 200) or len(response.data) != count
            or received.get("etag") != f'"{grant.version}"'
            or received.get("content-range") != expected_range
            or received.get("content-encoding", "identity") != "identity"):
        raise ContractError("the download response does not match the requested file version and range")
    return response.data


def download_artifact(*, output: str | Path, acquire: Callable[[str | None], ArtifactDownloadGrant],
                      timeout_seconds: float, workspace_key: str, site_id: str,
                      run_ref: str, artifact_ref: str,
                      cancelled: Callable[[], bool] | None = None) -> dict[str, object]:
    """Keep partial data private; a hard link publishes without replacing any path."""
    destination = Path(output).absolute()
    directory = private_directory = descriptor = None
    temporary = ".sai-download-" + secrets.token_hex(16)
    created_directory = False

    def check_cancelled() -> None:
        if cancelled is not None and cancelled():
            raise SaiCliError(code="download_cancelled", message="artifact download cancelled", exit_code=130)

    try:
        directory = os.open(destination.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        try:
            os.stat(destination.name, dir_fd=directory, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise ConfigError("the output path already exists", code="output_exists")
        check_cancelled()
        grant = acquire(None)
        initial = grant
        os.mkdir(temporary, 0o700, dir_fd=directory)
        created_directory = True
        private_directory = os.open(temporary, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                                    dir_fd=directory)
        metadata = os.fstat(private_directory)
        if metadata.st_uid != os.geteuid() or metadata.st_mode & 0o077:
            raise ConfigError("the temporary download directory is not private")
        descriptor = os.open("content.part", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                             0o600, dir_fd=private_directory)
        offset = 0
        while True:
            check_cancelled()
            if time.time() >= initial.transfer_until:
                raise AuthenticationError("the artifact transfer window has expired")
            if time.time() >= grant.expires_at:
                grant = acquire(initial.version)
            for attempt in range(2):
                if (grant.version != initial.version or grant.size_bytes != initial.size_bytes
                        or grant.download_url != initial.download_url or grant.download_name != initial.download_name):
                    raise ContractError("the file changed while downloading")
                try:
                    data = _read_range(grant, offset, timeout_seconds=timeout_seconds)
                    break
                except AuthenticationError:
                    if attempt:
                        raise
                    grant = acquire(initial.version)
            check_cancelled()
            view = memoryview(data)
            while view:
                written = os.write(descriptor, view)
                if written <= 0:
                    raise OSError("short local write")
                view = view[written:]
            offset += len(data)
            if offset == initial.size_bytes:
                break
        if os.fstat(descriptor).st_size != initial.size_bytes:
            raise ContractError("the local download is incomplete")
        os.fsync(descriptor)
        check_cancelled()
        # The source entry is inside an owner-only directory held by descriptor.
        os.link("content.part", destination.name, src_dir_fd=private_directory,
                dst_dir_fd=directory, follow_symlinks=False)
        os.fsync(directory)
        return {"schema_version": "compute.run-artifact-saved/v1", "workspace_key": workspace_key,
                "site_id": site_id, "run_ref": run_ref, "artifact_ref": artifact_ref,
                "output": str(destination), "size_bytes": initial.size_bytes, "version": initial.version}
    except FileExistsError as exc:
        raise ConfigError("the output path already exists", code="output_exists") from exc
    except OSError as exc:
        raise ConfigError("the artifact could not be saved to the output path", code="output_unavailable") from exc
    finally:
        failed = sys.exc_info()[0] is not None
        cleanup_error = None
        if private_directory is not None and descriptor is not None:
            try:
                os.unlink("content.part", dir_fd=private_directory)
            except OSError as exc:
                cleanup_error = exc
        if created_directory:
            try:
                os.rmdir(temporary, dir_fd=directory)
            except OSError as exc:
                cleanup_error = exc
        for opened in (descriptor, private_directory, directory):
            if opened is not None:
                try:
                    os.close(opened)
                except OSError as exc:
                    cleanup_error = exc
        if cleanup_error is not None and not failed:
            raise ConfigError("the download temporary directory could not be removed", code="output_cleanup_failed") from cleanup_error
