"""Protected on-disk cache for short-lived Bearer tokens."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
from typing import Any

from .errors import AuthenticationError


_MAX_CACHE_BYTES = 1_048_576


def cache_key(*, base_url: str, username: str, key_id: str) -> str:
    material = "\0".join((base_url.rstrip("/"), username, key_id)).encode("utf-8")
    return hashlib.sha256(material).hexdigest()


class TokenCache:
    def __init__(self, path: Path, *, enabled: bool = True) -> None:
        self.path = path
        self.enabled = enabled

    def _secure_parent(self) -> None:
        parent = self.path.parent
        parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        info = parent.stat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
            raise AuthenticationError("the token cache directory is not owned by the current user")
        if stat.S_IMODE(info.st_mode) != 0o700:
            os.chmod(parent, 0o700)

    def _read(self) -> dict[str, Any]:
        if not self.enabled:
            return {"version": 1, "entries": {}}
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
        payload = self._read()
        entry = payload["entries"].get(key)
        if not isinstance(entry, dict):
            return None
        token = entry.get("token")
        expires_at = entry.get("expires_at")
        if not isinstance(token, str) or not token or isinstance(expires_at, bool) or not isinstance(expires_at, int):
            return None
        if expires_at - now <= margin_seconds:
            return None
        return token, expires_at

    def put(self, key: str, *, token: str, expires_at: int) -> None:
        if not self.enabled:
            return
        self._secure_parent()
        payload = self._read()
        payload["entries"][key] = {"token": token, "expires_at": expires_at}
        encoded = (json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
        if len(encoded) > _MAX_CACHE_BYTES:
            raise AuthenticationError("the token cache is too large")

        self._write(encoded, error_message="the token cache could not be written")

    def delete(self, key: str) -> None:
        if not self.enabled or not self.path.exists():
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
