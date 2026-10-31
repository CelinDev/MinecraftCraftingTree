"""Discovery of Minecraft Modpack instances, JARs, loaded mod IDs, and configuration paths."""

from __future__ import annotations

import json
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ModpackInstanceInfo:
    """Metadata and resolved file paths for a local Minecraft modpack installation."""

    instance_dir: Path
    name: str = "Unknown Modpack"
    modpack_version: str = "unknown"
    minecraft_version: str = "1.20.1"
    mod_loader: str = "forge"
    vanilla_jar: Path | None = None
    mod_jars: list[Path] = field(default_factory=list)
    loaded_mod_ids: set[str] = field(default_factory=lambda: {"minecraft", "forge", "kubejs"})
    kubejs_dir: Path | None = None
    config_dir: Path | None = None


def _extract_mod_ids_from_mods_toml(toml_text: str) -> list[str]:
    """Extract all modId="..." declarations from META-INF/mods.toml."""
    return re.findall(r'modId\s*=\s*["\']([a-zA-Z0-9_.-]+)["\']', toml_text)


def discover_instance(
    instance_dir: str | Path,
    curseforge_install_dir: str | Path | None = None,
) -> ModpackInstanceInfo:
    """Inspect a modpack directory and discover its metadata, JARs, and loaded mod IDs."""
    inst_path = Path(instance_dir).resolve()
    if not inst_path.exists():
        raise FileNotFoundError(f"Instance directory not found: {inst_path}")

    info = ModpackInstanceInfo(instance_dir=inst_path, name=inst_path.name)

    manifest_path = inst_path / "manifest.json"
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8", errors="replace"))
            info.name = manifest.get("name", info.name)
            info.modpack_version = manifest.get("version", info.modpack_version)
            mc_section = manifest.get("minecraft", {})
            info.minecraft_version = mc_section.get("version", info.minecraft_version)
            loaders = mc_section.get("modLoaders", [])
            if loaders:
                info.mod_loader = loaders[0].get("id", info.mod_loader)
        except Exception:
            pass

    if curseforge_install_dir is None:
        # Check standard CurseForge Install sibling directory: ../../Install
        candidate_install = inst_path.parent.parent / "Install"
        if candidate_install.exists():
            curseforge_install_dir = candidate_install

    if curseforge_install_dir is not None:
        v_jar = (
            Path(curseforge_install_dir)
            / "versions"
            / info.minecraft_version
            / f"{info.minecraft_version}.jar"
        )
        if v_jar.exists():
            info.vanilla_jar = v_jar

    mods_dir = inst_path / "mods"
    if mods_dir.exists():
        info.mod_jars = sorted(mods_dir.glob("*.jar"), key=lambda p: p.name.lower())
        for jar_path in info.mod_jars:
            try:
                with zipfile.ZipFile(jar_path, "r") as zf:
                    if "META-INF/mods.toml" in zf.namelist():
                        toml_text = zf.read("META-INF/mods.toml").decode("utf-8", errors="replace")
                        for mod_id in _extract_mod_ids_from_mods_toml(toml_text):
                            info.loaded_mod_ids.add(mod_id)
                    # Also infer namespaces from data/<namespace>/ inside the JAR
                    for entry in zf.namelist():
                        if entry.startswith("data/"):
                            parts = entry.split("/")
                            if len(parts) > 2 and parts[1]:
                                info.loaded_mod_ids.add(parts[1])
            except Exception:
                continue

    kubejs_path = inst_path / "kubejs"
    if kubejs_path.exists():
        info.kubejs_dir = kubejs_path

    config_path = inst_path / "config"
    if config_path.exists():
        info.config_dir = config_path

    return info

