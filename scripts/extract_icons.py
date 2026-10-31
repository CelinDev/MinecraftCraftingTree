"""Script to pre-extract all item, block and machine textures to static disk files."""

from __future__ import annotations

import re
import shutil
import time
import zipfile
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
INSTANCE_DIR = Path(r"C:\Users\olx\curseforge\minecraft\Instances\Project Infinity 0.1")
VANILLA_JAR = Path(r"C:\Users\olx\curseforge\minecraft\Install\versions\1.20.1\1.20.1.jar")
ICONS_OUT_DIR = ROOT_DIR / "data" / "icons"

_TEXTURE_RE = re.compile(r"^assets/([^/]+)/textures/(item|block)/(.+)\.png$")


def save_icon(data: bytes, ns: str, name_variant: str, count_ref: list[int]) -> None:
    clean_name = name_variant.replace("/", "_").strip()
    if not clean_name:
        return
    out_file = ICONS_OUT_DIR / f"{ns}__{clean_name}.png"
    if not out_file.exists():
        out_file.write_bytes(data)
        count_ref[0] += 1


def extract_all_icons() -> None:
    ICONS_OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[*] Pre-extracting item and machine icons to: {ICONS_OUT_DIR}")
    t0 = time.perf_counter()
    count = [0]

    # 1. Extract Vanilla 1.20.1 textures
    if VANILLA_JAR.exists():
        with zipfile.ZipFile(VANILLA_JAR, "r") as zf:
            for name in zf.namelist():
                m = _TEXTURE_RE.match(name)
                if not m:
                    continue
                ns, kind, item_name = m.groups()
                data = zf.read(name)
                save_icon(data, ns, item_name, count)
                # Also save basename if nested
                base = Path(item_name).name
                if base != item_name:
                    save_icon(data, ns, base, count)

    # 2. Extract All Mod JARs textures
    mods_dir = INSTANCE_DIR / "mods"
    if mods_dir.exists():
        for jar_path in sorted(mods_dir.glob("*.jar")):
            try:
                with zipfile.ZipFile(jar_path, "r") as zf:
                    for name in zf.namelist():
                        m = _TEXTURE_RE.match(name)
                        if not m:
                            continue
                        ns, kind, item_name = m.groups()
                        data = zf.read(name)
                        # Save full joined path (e.g. crusher_front)
                        save_icon(data, ns, item_name, count)
                        base = Path(item_name).name
                        if base != item_name:
                            save_icon(data, ns, base, count)
                        
                        # Machine folder parent (e.g. block/crusher/front.png -> crusher)
                        parts = item_name.split("/")
                        if len(parts) >= 2 and parts[-1] in ("front", "front_active", "top", "side"):
                            parent_machine = parts[-2]
                            save_icon(data, ns, parent_machine, count)
            except Exception:
                continue

    # 3. Copy KubeJS assets textures (highest priority)
    kubejs_assets = INSTANCE_DIR / "kubejs" / "assets"
    if kubejs_assets.exists():
        for png_file in kubejs_assets.rglob("*.png"):
            path_str = png_file.as_posix()
            if "/textures/" in path_str:
                parts = path_str.split("/assets/")[-1].split("/")
                ns = parts[0]
                clean_name = png_file.stem
                out_file = ICONS_OUT_DIR / f"{ns}__{clean_name}.png"
                shutil.copy2(png_file, out_file)
                count[0] += 1

    # 4. Standard Machine Aliases
    machine_aliases: dict[str, str] = {
        # Vanilla
        "minecraft__crafting_table.png": "minecraft__crafting_table_front.png",
        "minecraft__stonecutter.png": "minecraft__stonecutter_side.png",
        "minecraft__furnace.png": "minecraft__furnace_front.png",
        "minecraft__blast_furnace.png": "minecraft__blast_furnace_front.png",
        "minecraft__smoker.png": "minecraft__smoker_front.png",
        "minecraft__smithing_table.png": "minecraft__smithing_table_front.png",
        # Botany Pots
        "botanypots__terracotta_botany_pot.png": "minecraft__flower_pot.png",
        "botanypots__soil.png": "minecraft__soul_soil.png",
        # Ex Deorum
        "exdeorum__oak_sieve.png": "exdeorum__mechanical_sieve_front.png",
        # Botania
        "botania__mana_pool.png": "botania__mana_pool_side.png",
        # Avaritia
        "avaritia__extreme_crafting_table.png": "avaritia__nether_crafting_table_top.png",
        # Extended Crafting
        "extendedcrafting__compressor.png": "extendedcrafting__compressor_front.png",
        "extendedcrafting__crafting_table.png": "extendedcrafting__advanced_table_top.png",
        # Hostile Neural Networks
        "hostilenetworks__loot_fabricator.png": "hostilenetworks__loot_fabricator_north.png",
        # Mystical Agriculture
        "mysticalagriculture__seed_reprocessor.png": "mysticalagriculture__seed_reprocessor_front.png",
        # Blood Magic
        "bloodmagic__arc.png": "bloodmagic__arc_front.png",
        # Masterful Machinery multiblocks
        "mm__neoeco_crafting_multiblock.png": "kubejs__neoeco_crafting_multiblock.png",
        "mm__neoeco_computation_multiblock.png": "kubejs__neoeco_computation_multiblock.png",
        "mm__neoeco_storage_multiblock.png": "kubejs__neoeco_storage_multiblock.png",
    }

    # Thermal machine aliases (use Thermal Extra machine textures or machine frame)
    thermal_extra_source = ICONS_OUT_DIR / "thermal_extra__machine_metal_infuser.png"
    if not thermal_extra_source.exists():
        thermal_extra_source = ICONS_OUT_DIR / "thermal__machine_frame.png"
    if not thermal_extra_source.exists():
        thermal_extra_source = ICONS_OUT_DIR / "minecraft__furnace_front.png"

    for th_machine in [
        "thermal__machine_press.png",
        "thermal__machine_smelter.png",
        "thermal__machine_pulverizer.png",
        "thermal__machine_crucible.png",
        "thermal__machine_chiller.png",
        "thermal__centrifuge.png",
        "thermal__machine_bottler.png",
        "thermal__machine_insolator.png",
        "thermal__machine_pyrolyzer.png",
        "thermal__machine_sawmill.png",
    ]:
        machine_aliases[th_machine] = thermal_extra_source.name

    for target_name, source_name in machine_aliases.items():
        src = ICONS_OUT_DIR / source_name
        dst = ICONS_OUT_DIR / target_name
        if src.exists() and not dst.exists():
            shutil.copy2(src, dst)
            count[0] += 1

    elapsed = time.perf_counter() - t0
    print(f"[+] Total new/updated icons: {count[0]} in {elapsed:.2f}s!")


if __name__ == "__main__":
    extract_all_icons()
