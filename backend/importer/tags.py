"""Tag registry and Almost Unified priority resolver."""

from __future__ import annotations

import json
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from backend.models.recipe import normalize_identifier


@dataclass
class TagRegistry:
    """Stores item, block, fluid, and gas tags and resolves preferred items via Almost Unified."""

    item_tags: dict[str, list[str]] = field(default_factory=dict)
    fluid_tags: dict[str, list[str]] = field(default_factory=dict)
    mod_priorities: list[str] = field(
        default_factory=lambda: ["minecraft", "kubejs", "thermal", "mekanism", "common_ore_library"]
    )
    priority_overrides: dict[str, str] = field(default_factory=dict)
    _resolved_cache: dict[str, list[str]] = field(default_factory=dict)

    def add_tag_data(self, tag_id: str, data: dict[str, Any], is_fluid: bool = False) -> None:
        """Merge a Minecraft tag JSON object ({replace: bool, values: [...]}) into the registry."""
        norm_tag = normalize_identifier(tag_id.lstrip("#"))
        target_map = self.fluid_tags if is_fluid else self.item_tags
        replace = bool(data.get("replace", False))
        current = [] if replace else list(target_map.get(norm_tag, []))

        values = data.get("values", [])
        if not isinstance(values, list):
            return

        for entry in values:
            val_str: str | None = None
            if isinstance(entry, str):
                val_str = entry
            elif isinstance(entry, dict) and "id" in entry:
                val_str = str(entry["id"])
            if val_str:
                norm_val = normalize_identifier(val_str)
                if norm_val not in current:
                    current.append(norm_val)

        target_map[norm_tag] = current
        self._resolved_cache.clear()

    def add_items_to_tag(self, tag_id: str, items: list[str] | str) -> None:
        """Programmatically add one or more items/subtags to an item tag (e.g. from KubeJS tags.js)."""
        norm_tag = normalize_identifier(tag_id.lstrip("#"))
        current = self.item_tags.setdefault(norm_tag, [])
        item_list = [items] if isinstance(items, str) else items
        for item in item_list:
            if not item or item.startswith("/"):
                continue
            norm_item = normalize_identifier(item)
            if norm_item not in current:
                current.append(norm_item)
        self._resolved_cache.clear()

    def remove_items_from_tag(self, tag_id: str, items: list[str] | str) -> None:
        """Programmatically remove one or more items from an item tag."""
        norm_tag = normalize_identifier(tag_id.lstrip("#"))
        if norm_tag not in self.item_tags:
            return
        item_list = [items] if isinstance(items, str) else items
        norm_to_remove = {normalize_identifier(i) for i in item_list if i}
        self.item_tags[norm_tag] = [x for x in self.item_tags[norm_tag] if x not in norm_to_remove]
        self._resolved_cache.clear()

    def remove_all_from_tag(self, tag_id: str) -> None:
        """Clear all entries from a specific item tag."""
        norm_tag = normalize_identifier(tag_id.lstrip("#"))
        self.item_tags[norm_tag] = []
        self._resolved_cache.clear()

    def load_almost_unified_config(self, config_path: Path) -> None:
        """Load modPriorities and priorityOverrides from config/almostunified/unify.json."""
        if not config_path.exists():
            return
        try:
            data = json.loads(config_path.read_text(encoding="utf-8", errors="replace"))
            if "modPriorities" in data and isinstance(data["modPriorities"], list):
                self.mod_priorities = [str(m) for m in data["modPriorities"]]
            if "priorityOverrides" in data and isinstance(data["priorityOverrides"], dict):
                self.priority_overrides = {
                    normalize_identifier(k.lstrip("#")): str(v)
                    for k, v in data["priorityOverrides"].items()
                }
        except Exception:
            pass

    def get_tag_items(self, tag_id: str, visited: set[str] | None = None) -> list[str]:
        """Recursively resolve a tag ID into its concrete item IDs, ordered by mod priority."""
        norm_tag = normalize_identifier(tag_id.lstrip("#"))
        if norm_tag in self._resolved_cache:
            return list(self._resolved_cache[norm_tag])

        if visited is None:
            visited = set()
        if norm_tag in visited:
            return []
        visited.add(norm_tag)

        raw_entries = self.item_tags.get(norm_tag, [])
        concrete: list[str] = []
        for entry in raw_entries:
            if entry.startswith("#"):
                for sub_item in self.get_tag_items(entry[1:], visited):
                    if sub_item not in concrete:
                        concrete.append(sub_item)
            else:
                if entry not in concrete:
                    concrete.append(entry)

        # Sort by Almost Unified priority if applicable
        override_mod = self.priority_overrides.get(norm_tag)

        def _priority_key(item_id: str) -> tuple[int, int, str]:
            mod_ns = item_id.split(":", 1)[0] if ":" in item_id else "minecraft"
            if override_mod and mod_ns == override_mod:
                return (0, 0, item_id)
            if mod_ns in self.mod_priorities:
                return (1, self.mod_priorities.index(mod_ns), item_id)
            return (2, 999, item_id)

        sorted_items = sorted(concrete, key=_priority_key)
        self._resolved_cache[norm_tag] = sorted_items
        return list(sorted_items)

    def get_preferred_item(self, tag_id: str) -> str | None:
        """Return the highest-priority concrete item for a given tag, if any."""
        items = self.get_tag_items(tag_id)
        return items[0] if items else None


_TAG_PATH_RE = re.compile(r"^data/([^/]+)/tags/(items|fluids)/(.+)\.json$")


def load_tags_from_jar(jar_path: Path, registry: TagRegistry) -> None:
    """Extract and load all item and fluid tag JSONs from a JAR file."""
    if not jar_path or not jar_path.exists():
        return
    try:
        with zipfile.ZipFile(jar_path, "r") as zf:
            for name in zf.namelist():
                m = _TAG_PATH_RE.match(name)
                if not m:
                    continue
                namespace, kind, tag_subpath = m.groups()
                tag_id = f"{namespace}:{tag_subpath}"
                try:
                    raw = zf.read(name).decode("utf-8", errors="replace")
                    data = json.loads(raw)
                    if isinstance(data, dict):
                        registry.add_tag_data(tag_id, data, is_fluid=(kind == "fluids"))
                except Exception:
                    continue
    except Exception:
        return


def load_tags_from_datapack_dir(data_dir: Path, registry: TagRegistry) -> None:
    """Load item and fluid tag JSONs from an unpacked datapack directory (e.g. kubejs/data)."""
    if not data_dir or not data_dir.exists():
        return
    for namespace_dir in sorted(data_dir.iterdir()):
        if not namespace_dir.is_dir():
            continue
        namespace = namespace_dir.name
        for kind in ("items", "fluids"):
            tags_root = namespace_dir / "tags" / kind
            if not tags_root.exists():
                continue
            for json_file in sorted(tags_root.rglob("*.json")):
                rel = json_file.relative_to(tags_root).with_suffix("").as_posix()
                tag_id = f"{namespace}:{rel}"
                try:
                    data = json.loads(json_file.read_text(encoding="utf-8", errors="replace"))
                    if isinstance(data, dict):
                        registry.add_tag_data(tag_id, data, is_fluid=(kind == "fluids"))
                except Exception:
                    continue


def apply_kubejs_tag_scripts(server_scripts_dir: Path, registry: TagRegistry) -> None:
    """Parse KubeJS ServerEvents.tags('item', ...) calls (such as kubejs/server_scripts/tags.js)."""
    if not server_scripts_dir or not server_scripts_dir.exists():
        return
    for js_file in sorted(server_scripts_dir.rglob("*.js")):
        try:
            text = js_file.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        if "ServerEvents.tags" not in text:
            continue

        # Remove single-line comments
        clean_lines = [
            line for line in text.splitlines() if not line.strip().startswith("//")
        ]
        clean_text = "\n".join(clean_lines)

        # Match event.removeAll('tag')
        for m in re.finditer(r"\.removeAll\s*\(\s*['\"]([^'\"]+)['\"]\s*\)", clean_text):
            registry.remove_all_from_tag(m.group(1))

        # Match event.add('tag', 'item' or ['item1', 'item2'])
        for m in re.finditer(
            r"\.add\s*\(\s*['\"]([^'\"]+)['\"]\s*,\s*(\[[^\]]*\]|['\"][^'\"]+['\"])\s*\)",
            clean_text,
        ):
            tag_id = m.group(1)
            rhs = m.group(2)
            items = re.findall(r"['\"]([^'\"]+)['\"]", rhs)
            registry.add_items_to_tag(tag_id, items)

        # Match event.remove('tag', 'item' or ['item1', 'item2'])
        for m in re.finditer(
            r"\.remove\s*\(\s*['\"]([^'\"]+)['\"]\s*,\s*(\[[^\]]*\]|['\"][^'\"]+['\"])\s*\)",
            clean_text,
        ):
            tag_id = m.group(1)
            rhs = m.group(2)
            items = re.findall(r"['\"]([^'\"]+)['\"]", rhs)
            registry.remove_items_from_tag(tag_id, items)

