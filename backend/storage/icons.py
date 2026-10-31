"""Item icon resolver and texture extractor for Minecraft Vanilla, KubeJS, and Mod JARs."""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

_TEXTURE_PATH_RE = re.compile(r"^assets/([^/]+)/textures/(item|block)/(.+)\.png$")


class IconService:
    """Discovers and serves PNG texture icons for Minecraft items and blocks."""

    def __init__(
        self,
        kubejs_assets_dir: Path | None,
        vanilla_jar_path: Path | None,
        mod_jars: list[Path],
    ) -> None:
        self.kubejs_assets_dir = kubejs_assets_dir
        self.vanilla_jar_path = vanilla_jar_path
        self.mod_jars = mod_jars
        self._cache: dict[str, bytes | None] = {}
        # Pre-index mod jars by namespace
        self._namespace_to_jars: dict[str, list[Path]] = {}
        self._build_jar_index()

    def _build_jar_index(self) -> None:
        """Map each namespace to the mod JARs containing assets for it."""
        for jar in self.mod_jars:
            jar_name = jar.name.lower()
            # Fast heuristic mapping from jar filename
            base_mod = jar_name.split("-")[0].split("_")[0]
            self._namespace_to_jars.setdefault(base_mod, []).append(jar)

    def get_item_icon(self, raw_id: str) -> bytes | None:
        """Fetch the PNG bytes for a given item_id (e.g. 'minecraft:iron_ingot' or 'kubejs:infinity_1')."""
        clean_id = raw_id.strip()
        if clean_id.startswith("#"):
            clean_id = clean_id[1:]
        if clean_id in self._cache:
            return self._cache[clean_id]

        if ":" not in clean_id:
            clean_id = f"minecraft:{clean_id}"

        ns, name = clean_id.split(":", 1)
        name_clean = name.split("{")[0]  # Remove NBT if present

        png_bytes = (
            self._search_kubejs(ns, name_clean)
            or self._search_vanilla(ns, name_clean)
            or self._search_mods(ns, name_clean)
        )

        self._cache[clean_id] = png_bytes
        return png_bytes

    def _search_kubejs(self, ns: str, name: str) -> bytes | None:
        """Search in kubejs/assets/<ns>/textures/(item|block)/."""
        if not self.kubejs_assets_dir or not self.kubejs_assets_dir.exists():
            return None

        # 1. Direct path check
        candidates = [
            self.kubejs_assets_dir / ns / "textures" / "item" / f"{name}.png",
            self.kubejs_assets_dir / ns / "textures" / "block" / f"{name}.png",
            # Subfolder special cases in Project Infinity (e.g. infinityingot/, mysticalagriculture/)
            self.kubejs_assets_dir / ns / "textures" / "item" / "infinityingot" / f"{name}.png",
            self.kubejs_assets_dir / ns / "textures" / "item" / "mysticalagriculture" / f"{name}.png",
            self.kubejs_assets_dir / ns / "textures" / "item" / "silent" / f"{name}.png",
            self.kubejs_assets_dir / ns / "textures" / "item" / "mekanism" / f"{name}.png",
            self.kubejs_assets_dir / ns / "textures" / "item" / "enderio" / f"{name}.png",
            self.kubejs_assets_dir / ns / "textures" / "item" / "draconic" / f"{name}.png",
            self.kubejs_assets_dir / ns / "textures" / "item" / "powah" / f"{name}.png",
        ]
        for c in candidates:
            if c.exists() and c.is_file():
                return c.read_bytes()

        # 2. Fuzzy search inside ns folder if not found directly
        ns_dir = self.kubejs_assets_dir / ns / "textures"
        if ns_dir.exists():
            for p in ns_dir.rglob(f"{name}.png"):
                if p.is_file():
                    return p.read_bytes()

        return None

    def _search_vanilla(self, ns: str, name: str) -> bytes | None:
        """Search inside 1.20.1.jar for vanilla items/blocks."""
        if ns != "minecraft" or not self.vanilla_jar_path or not self.vanilla_jar_path.exists():
            return None
        try:
            with zipfile.ZipFile(self.vanilla_jar_path, "r") as zf:
                for folder in ("item", "block"):
                    path = f"assets/minecraft/textures/{folder}/{name}.png"
                    if path in zf.namelist():
                        return zf.read(path)
        except Exception:
            return None
        return None

    def _search_mods(self, ns: str, name: str) -> bytes | None:
        """Search inside mod JARs matching the namespace."""
        # Check candidate jars for this namespace
        candidates: list[Path] = []
        for jar in self.mod_jars:
            jar_lower = jar.name.lower()
            if ns.lower() in jar_lower:
                candidates.append(jar)

        # Fallback to scanning all if no name match
        search_jars = candidates if candidates else self.mod_jars[:40]

        for jar in search_jars:
            try:
                with zipfile.ZipFile(jar, "r") as zf:
                    for folder in ("item", "block"):
                        entry = f"assets/{ns}/textures/{folder}/{name}.png"
                        if entry in zf.namelist():
                            return zf.read(entry)
            except Exception:
                continue
        return None

