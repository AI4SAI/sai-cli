"""Protected on-disk cache for opaque SAI credentials.

The same hardened store is used for the short-lived access token cache and
the separately located, longer-lived device refresh credential.  Callers keep
the two namespaces/files separate; this module only owns filesystem safety and
atomic replacement.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
import time
from typing import Any, Callable

from .errors import AuthenticationError


_MAX_CACHE_BYTES = 1_048_576


def cache_key(*, base_url: str, username: str, key_id: str) -> str:
    material = "\0".join((base_url.rstrip("/"), username, key_id)).encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def device_access_cache_key(*, base_url: str) -> str:
    """Return the stable namespace key for a CLI device access token."""

    return cache_key(
        base_url=base_url,
        username="__sai_cli_device__",
        key_id="cli-device-access",
    )


def device_refresh_cache_key(*, base_url: str) -> str:
    """Return the stable namespace key for a CLI device refresh token."""

    return cache_key(
        base_url=base_url,
        username="__sai_cli_device__",
        key_id="cli-device-refresh",
    )


def device_pending_cache_key(*, base_url: str) -> str:
    """Return the stable namespace key for a pending device authorization."""

    return cache_key(
        base_url=base_url,
        username="__sai_cli_device__",
        key_id="cli-device-pending",
    )


class TokenCache:
    def __init__(
        self,
        path: Path,
        *,
        enabled: bool = True,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.path = path
        self.enabled = enabled
        self.clock = clock

    def _secure_parent(self) -> None:
        parent = self.path.parent
        self._reject_symlink_ancestors(parent)
        try:
            info = parent.lstat()
        except FileNotFoundError:
            parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            info = parent.lstat()
        if (
            stat.S_ISLNK(info.st_mode)
            or not stat.S_ISDIR(info.st_mode)
            or info.st_uid != os.getuid()
        ):
            raise AuthenticationError("the token cache directory is not owned by the current user")
        if stat.S_IMODE(info.st_mode) != 0o700:
            os.chmod(parent, 0o700)

    @staticmethod
    def _reject_symlink_ancestors(path: Path) -> None:
        """Reject a cache path redirected through any existing symlink."""

        current = path
        while True:
            try:
                info = current.lstat()
            except FileNotFoundError:
                current = current.parent
                if current == path:
                    break
                if current == current.parent:
                    break
                continue
            except OSError as exc:
                raise AuthenticationError(
                    "the token cache directory could not be inspected"
                ) from exc
            if stat.S_ISLNK(info.st_mode):
                raise AuthenticationError(
                    "the token cache directory must not contain symbolic links"
                )
            if current == current.parent:
                break
            current = current.parent

    def _read(self) -> dict[str, Any]:
        if not self.enabled:
            return {"version": 1, "entries": {}}
        self._reject_symlink_ancestors(self.path.parent)
        try:
            info = self.path.lstat()
        except FileNotFoundError:
            return {"version": 1, "entries": {}}
        try:
            if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
                raise AuthenticationError("the token cache must be a regular file")
            if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
                raise AuthenticationError("the token cache permissions are not private")
            if info.st_size > _MAX_CACHE_BYTES:
                raise AuthenticationError("the token cache is too large")
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            descriptor = os.open(self.path, flags)
            with os.fdopen(descriptor, "rb") as handle:
                opened = os.fstat(handle.fileno())
                if (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino):
                    raise AuthenticationError("the token cache changed while it was being read")
                data = handle.read(_MAX_CACHE_BYTES + 1)
            if len(data) > _MAX_CACHE_BYTES:
                raise AuthenticationError("the token cache is too large")
            payload = json.loads(data.decode("utf-8", errors="strict"))
        except AuthenticationError:
            raise
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise AuthenticationError("the token cache could not be read") from exc
        if not isinstance(payload, dict) or payload.get("version") != 1:
            raise AuthenticationError("the token cache format is invalid")
        entries = payload.get("entries")
        if not isinstance(entries, dict):
            raise AuthenticationError("the token cache format is invalid")
        return payload

    def get(self, key: str, *, now: int, margin_seconds: int = 30) -> tuple[str, int] | None:
        if isinstance(now, bool) or not isinstance(now, int) or now < 0:
            raise AuthenticationError("the token cache clock value is invalid")
        if (
            isinstance(margin_seconds, bool)
            or not isinstance(margin_seconds, int)
            or margin_seconds < 0
        ):
            raise AuthenticationError("the token cache expiry margin is invalid")
        payload = self._read()
        entries = payload["entries"]
        if key not in entries:
            return None
        entry = entries[key]
        if not isinstance(entry, dict):
            raise AuthenticationError("the token cache entry is invalid")
        token = entry.get("token")
        expires_at = entry.get("expires_at")
        if (
            not isinstance(token, str)
            or not token
            or len(token) > 16_384
            or any(ord(char) < 32 or ord(char) == 127 for char in token)
            or isinstance(expires_at, bool)
            or not isinstance(expires_at, int)
        ):
            raise AuthenticationError("the token cache entry is invalid")
        if expires_at < 1:
            raise AuthenticationError("the token cache entry is invalid")
        if expires_at - now <= margin_seconds:
            return None
        return token, expires_at

    def put(self, key: str, *, token: str, expires_at: int) -> None:
        if not self.enabled:
            return
        if (
            not isinstance(token, str)
            or not token
            or len(token) > 16_384
            or any(ord(char) < 32 or ord(char) == 127 for char in token)
            or isinstance(expires_at, bool)
            or not isinstance(expires_at, int)
            or expires_at < 1
        ):
            raise AuthenticationError("the token cache entry is invalid")
        self._secure_parent()
        payload = self._read()
        now = int(self.clock())
        payload["entries"] = {
            entry_key: entry
            for entry_key, entry in payload["entries"].items()
            if isinstance(entry, dict)
            and isinstance(entry.get("expires_at"), int)
            and not isinstance(entry.get("expires_at"), bool)
            and entry["expires_at"] - now > 0
        }
        payload["entries"][key] = {"token": token, "expires_at": expires_at}
        encoded = (json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
        if len(encoded) > _MAX_CACHE_BYTES:
            raise AuthenticationError("the token cache is too large")

        self._write(encoded, error_message="the token cache could not be written")

    def delete(self, key: str) -> None:
        if not self.enabled:
            return
        try:
            self.path.lstat()
        except FileNotFoundError:
            return
        payload = self._read()
        if payload["entries"].pop(key, None) is None:
            return
        self._secure_parent()
        encoded = (json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
        self._write(encoded, error_message="the token cache could not be updated")

    def _write(self, encoded: bytes, *, error_message: str) -> None:
        temporary: str | None = None
        try:
            descriptor, temporary = tempfile.mkstemp(prefix=".token-cache-", dir=self.path.parent)
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
            temporary = None
            os.chmod(self.path, 0o600)
        except OSError as exc:
            raise AuthenticationError(error_message) from exc
        finally:
            if temporary:
                try:
                    os.unlink(temporary)
                except FileNotFoundError:
                    pass
