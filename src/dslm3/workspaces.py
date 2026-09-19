"""Local registry for multiple independent DSLM3 workspaces."""

from __future__ import annotations

import json
from pathlib import Path

from dslm3.common import DomainError, digest, dump_json

REGISTRY_SCHEMA = 1
REGISTRY_FILENAME = ".dslm3-workspaces.json"


class WorkspaceRegistry:
    def __init__(self, default_workspace: str | Path):
        default = Path(default_workspace).expanduser().resolve()
        self.path = default.parent / REGISTRY_FILENAME
        self._ensure(default)

    @staticmethod
    def workspace_id(path: str | Path) -> str:
        return "WS_" + digest(str(Path(path).expanduser().resolve()))[:16]

    @staticmethod
    def _label(value: str | None, path: Path) -> str:
        label = " ".join((value or path.name or str(path)).split()).strip()
        if not label:
            raise DomainError("workspace_name", "Il nome del workspace non può essere vuoto.")
        if len(label) > 80:
            raise DomainError("workspace_name", "Il nome del workspace è troppo lungo.")
        return label

    def _entry(self, path: str | Path, name: str | None = None) -> dict:
        resolved = Path(path).expanduser().resolve()
        return {
            "id": self.workspace_id(resolved),
            "name": self._label(name, resolved),
            "path": str(resolved),
        }

    def _load(self) -> dict:
        if not self.path.exists():
            return {"schema_version": REGISTRY_SCHEMA, "workspaces": []}
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise DomainError(
                "workspace_registry",
                f"Registry workspace non leggibile: {exc}",
            ) from exc
        if (
            not isinstance(value, dict)
            or value.get("schema_version") != REGISTRY_SCHEMA
            or not isinstance(value.get("workspaces"), list)
        ):
            raise DomainError("workspace_registry", "Formato registry workspace non valido.")
        normalized = []
        seen = set()
        for item in value["workspaces"]:
            if not isinstance(item, dict) or not isinstance(item.get("path"), str):
                raise DomainError("workspace_registry", "Voce workspace non valida.")
            entry = self._entry(item["path"], item.get("name"))
            if entry["id"] in seen:
                continue
            seen.add(entry["id"])
            normalized.append(entry)
        return {"schema_version": REGISTRY_SCHEMA, "workspaces": normalized}

    def _save(self, state: dict) -> None:
        dump_json(self.path, state)

    def _ensure(self, default: Path) -> None:
        state = self._load()
        ident = self.workspace_id(default)
        if not any(item["id"] == ident for item in state["workspaces"]):
            state["workspaces"].append(self._entry(default))
            self._save(state)

    def list(self, active: str | Path) -> dict:
        active_path = Path(active).expanduser().resolve()
        active_id = self.workspace_id(active_path)
        state = self._load()
        items = []
        for item in state["workspaces"]:
            path = Path(item["path"])
            ready = (
                path.is_dir()
                and (path / "registry.sqlite3").is_file()
                and (path / "project.json").is_file()
            )
            items.append(
                {
                    **item,
                    "active": item["id"] == active_id,
                    "available": ready,
                }
            )
        return {
            "registry": str(self.path),
            "active_id": active_id,
            "items": items,
        }

    def add(self, path: str | Path, name: str | None = None) -> dict:
        entry = self._entry(path, name)
        state = self._load()
        for item in state["workspaces"]:
            if item["id"] == entry["id"]:
                if name and item["name"] != entry["name"]:
                    item["name"] = entry["name"]
                    self._save(state)
                return item
            if item["name"].casefold() == entry["name"].casefold():
                raise DomainError(
                    "workspace_name_conflict",
                    "Esiste già un workspace con questo nome.",
                    409,
                )
        state["workspaces"].append(entry)
        self._save(state)
        return entry

    def get(self, ident: str) -> dict:
        state = self._load()
        for item in state["workspaces"]:
            if item["id"] == ident:
                return item
        raise DomainError("workspace_missing", "Workspace non registrato.", 404)

    def forget(self, ident: str, active: str | Path) -> dict:
        active_id = self.workspace_id(active)
        if ident == active_id:
            raise DomainError(
                "workspace_active",
                "Non è possibile dimenticare il workspace attivo.",
                409,
            )
        state = self._load()
        kept = [item for item in state["workspaces"] if item["id"] != ident]
        if len(kept) == len(state["workspaces"]):
            raise DomainError("workspace_missing", "Workspace non registrato.", 404)
        state["workspaces"] = kept
        self._save(state)
        return {"forgotten": ident}
