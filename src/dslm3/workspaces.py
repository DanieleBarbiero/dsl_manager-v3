"""Local registry for multiple independent DSLM3 workspaces."""

from __future__ import annotations

import json
from pathlib import Path

from dslm3.common import DomainError, digest, dump_json

REGISTRY_SCHEMA = 1
REGISTRY_FILENAME = ".dslm3-workspaces.json"


class WorkspaceRegistry:
    def __init__(self, workspaces_root: str | Path):
        self.root = Path(workspaces_root).expanduser().resolve()
        # The registry stays beside the container: startup must not create
        # anything inside workspaces/.
        self.path = self.root.parent / REGISTRY_FILENAME

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

    @staticmethod
    def _ready(path: Path) -> bool:
        return (
            path.is_dir()
            and (path / "registry.sqlite3").is_file()
            and (path / "project.json").is_file()
        )

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

    def _items(self) -> list[dict]:
        stored = self._load()["workspaces"]
        stored_by_id = {item["id"]: item for item in stored}
        items = []
        seen = set()
        if self.root.is_dir():
            children = sorted(
                (p for p in self.root.iterdir() if p.is_dir()),
                key=lambda p: (p.name.casefold(), p.name),
            )
            for child in children:
                if not self._ready(child):
                    continue
                ident = self.workspace_id(child)
                saved = stored_by_id.get(ident)
                entry = self._entry(child, saved.get("name") if saved else None)
                entry["discovered"] = True
                items.append(entry)
                seen.add(ident)
        for item in stored:
            if item["id"] in seen:
                continue
            items.append({**item, "discovered": False})
        return items

    def startup_workspace(self) -> Path | None:
        # Only children of workspaces/ are auto-activated. A legacy/external
        # registry entry remains selectable, but can never turn the container
        # itself into a workspace again.
        for item in self._items():
            if item["discovered"] and self._ready(Path(item["path"])):
                return Path(item["path"])
        return None

    def list(self, active: str | Path | None) -> dict:
        active_id = self.workspace_id(active) if active is not None else None
        items = []
        for item in self._items():
            path = Path(item["path"])
            items.append(
                {
                    **item,
                    "active": item["id"] == active_id,
                    "available": self._ready(path),
                }
            )
        return {
            "registry": str(self.path),
            "root": str(self.root),
            "active_id": active_id,
            "items": items,
        }

    def add(self, path: str | Path, name: str | None = None) -> dict:
        entry = self._entry(path, name)
        state = self._load()
        all_items = self._items()
        for item in all_items:
            if item["id"] == entry["id"]:
                if name and item["name"] != entry["name"]:
                    for saved in state["workspaces"]:
                        if saved["id"] == entry["id"]:
                            saved["name"] = entry["name"]
                            self._save(state)
                            break
                    else:
                        state["workspaces"].append(entry)
                        self._save(state)
                    item["name"] = entry["name"]
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
        for item in self._items():
            if item["id"] == ident:
                return item
        raise DomainError("workspace_missing", "Workspace non registrato.", 404)

    def forget(self, ident: str, active: str | Path | None) -> dict:
        active_id = self.workspace_id(active) if active is not None else None
        if ident == active_id:
            raise DomainError(
                "workspace_active",
                "Non è possibile dimenticare il workspace attivo.",
                409,
            )
        current = self.get(ident)
        if current.get("discovered"):
            raise DomainError(
                "workspace_discovered",
                "Un workspace presente sotto workspaces non può essere dimenticato: spostare o rimuovere la directory a server fermo.",
                409,
            )
        state = self._load()
        kept = [item for item in state["workspaces"] if item["id"] != ident]
        if len(kept) == len(state["workspaces"]):
            raise DomainError("workspace_missing", "Workspace non registrato.", 404)
        state["workspaces"] = kept
        self._save(state)
        return {"forgotten": ident}
