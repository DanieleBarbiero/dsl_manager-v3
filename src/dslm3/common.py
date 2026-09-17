from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unicodedata
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any


class DomainError(ValueError):
    def __init__(self, reason: str, message: str, status: int = 400):
        super().__init__(message)
        self.reason, self.status = reason, status


def canonical(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def digest(value: Any) -> str:
    return hashlib.sha256(
        value if isinstance(value, bytes) else canonical(value).encode()
    ).hexdigest()


def uid(prefix: str, value: Any) -> str:
    return prefix + "_" + digest(value)[:24]


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def name_key(value: str) -> str:
    return unicodedata.normalize("NFC", " ".join(value.split())).casefold()


def atomic_write(path: Path, data: str | bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = data.encode("utf-8") if isinstance(data, str) else data
    fd, temporary = tempfile.mkstemp(prefix=".tmp_", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def safe_relative(value: str) -> str:
    if not isinstance(value, str):
        raise DomainError("unsafe_path", "Il percorso deve essere testo.")
    value = value.replace("\\", "/")
    path = PurePosixPath(value)
    if (
        not value
        or path.is_absolute()
        or any(x in ("", ".", "..") for x in value.split("/"))
        or ":" in value
        or "\x00" in value
    ):
        raise DomainError(
            "unsafe_path", "Il percorso deve essere relativo e non contenere '..'."
        )
    return str(path)


def within(root: Path, relative: str) -> Path:
    path = root / safe_relative(relative)
    if not path.resolve().is_relative_to(root.resolve()):
        raise DomainError("unsafe_path", "Il percorso esce dal workspace.")
    return path


def dump_json(path: Path, value: Any) -> None:
    atomic_write(
        path,
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        + "\n",
    )
