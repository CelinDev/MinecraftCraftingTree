"""High-performance static icon service serving pre-extracted local icon files."""

from __future__ import annotations

import urllib.parse
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
STATIC_ICONS_DIR = ROOT_DIR / "data" / "icons"

_TRANSPARENT_1X1 = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06"
    b"\x00\x00\x00\x1f\x15c4\x00\x00\x00\rIDATx\x9cc`\x00\x00\x00\x02\x00\x01H\xaf"
    b"\xa4q\x00\x00\x00\x00IEND\xaeB`\x82"
)

DIRECT_FORGE_MAP: dict[str, str] = {
    "dusts/redstone": "minecraft__redstone.png",
    "dusts/glowstone": "minecraft__glowstone_dust.png",
    "gems/diamond": "minecraft__diamond.png",
    "gems/emerald": "minecraft__emerald.png",
    "gems/lapis": "minecraft__lapis_lazuli.png",
    "gems/quartz": "minecraft__quartz.png",
    "ingots/iron": "minecraft__iron_ingot.png",
    "ingots/gold": "minecraft__gold_ingot.png",
    "ingots/copper": "minecraft__copper_ingot.png",
    "ingots/netherite": "minecraft__netherite_ingot.png",
    "rods/wooden": "minecraft__stick.png",
    "rods/blaze": "minecraft__blaze_rod.png",
    "chests/wooden": "sophisticatedstorage__oak_chest.png",
    "barrels/wooden": "minecraft__barrel_top.png",
    "stone": "minecraft__stone.png",
    "cobblestone": "minecraft__cobblestone.png",
    "glass": "minecraft__glass.png",
    "glass_panes": "minecraft__glass_pane.png",
    "obsidian": "minecraft__obsidian.png",
    "ender_pearls": "minecraft__ender_pearl.png",
    "string": "minecraft__string.png",
    "leather": "minecraft__leather.png",
    "fe": "thermal__rf.png",
    "slimeballs": "minecraft__slime_ball.png",
    "nether_stars": "minecraft__nether_star.png",
    "eggs": "minecraft__egg.png",
    "feathers": "minecraft__feather.png",
    "gunpowder": "minecraft__gunpowder.png",
    "bones": "minecraft__bone.png",
    "crops/wheat": "minecraft__wheat.png",
    "plastic": "pneumaticcraft__plastic.png",
    "wool": "minecraft__white_wool.png",
    "blocks/wool": "minecraft__white_wool.png",
}

MACHINE_ICON_FALLBACKS: dict[str, str] = {
    "exdeorum:oak_barrel": "minecraft__barrel_top.png",
    "exdeorum:oak_crucible": "exdeorum__porcelain_crucible.png",
    "exdeorum:compressed_sieve": "exdeorum__oak_sieve.png",
    "bloodmagic:altar": "bloodmagic__altar.png",
    "bloodmagic:alchemytable": "bloodmagic__alchemytable.png",
    "bloodmagic:alchemyarray": "bloodmagic__alchemyarray.png",
    "nuclearcraft:kugelblitz_controller": "nuclearcraft__kugelblitz_controller_top.png",
    "nuclearcraft:collision_chamber_controller": "nuclearcraft__collision_chamber_controller.png",
    "nuclearcraft:decay_chamber_controller": "nuclearcraft__decay_chamber_controller.png",
    "thermal:centrifuge": "thermal__centrifuge.png",
    "thermal:machine_centrifuge": "thermal__centrifuge.png",
    "hostilenetworks:simulation_chamber": "hostilenetworks__simulation_chamber_north.png",
    "hostilenetworks:sim_chamber": "hostilenetworks__simulation_chamber_north.png",
    "avaritia:compressor": "avaritia__compressor_front.png",
    "avaritia:neutron_compressor": "avaritia__compressor_front.png",
}


class FastStaticIconService:
    """Delivers item and machine icons with zero ZIP extraction overhead."""

    def __init__(self, icons_dir: Path = STATIC_ICONS_DIR) -> None:
        self.icons_dir = icons_dir
        self.icons_dir.mkdir(parents=True, exist_ok=True)
        self._available_files: set[str] = set()
        self.refresh()

    def refresh(self) -> None:
        if self.icons_dir.exists():
            self._available_files = {f.name for f in self.icons_dir.glob("*.png")}

    def get_icon_path(self, raw_id: str) -> Path | None:
        if not raw_id:
            return None

        clean_id = urllib.parse.unquote(str(raw_id)).strip()
        if clean_id.startswith("#"):
            clean_id = clean_id[1:]
        if ":" not in clean_id:
            clean_id = f"minecraft:{clean_id}"

        ns, name = clean_id.split(":", 1)
        name_clean = name.split("{")[0].strip()

        # 0. Machine fallback overrides
        if clean_id in MACHINE_ICON_FALLBACKS:
            fb = MACHINE_ICON_FALLBACKS[clean_id]
            if fb in self._available_files:
                return self.icons_dir / fb

        # 1. Exact match: ns__name.png
        filename = f"{ns}__{name_clean}.png"
        if filename in self._available_files:
            return self.icons_dir / filename

        # 2. Masterful Machinery multiblock prefix
        if ns == "mm":
            f_mm = f"kubejs__{name_clean}.png"
            if f_mm in self._available_files:
                return self.icons_dir / f_mm

        # 3. Forge Tag Resolution
        if ns == "forge":
            if name_clean in DIRECT_FORGE_MAP and DIRECT_FORGE_MAP[name_clean] in self._available_files:
                return self.icons_dir / DIRECT_FORGE_MAP[name_clean]
            parts = name_clean.split("/")
            if len(parts) == 2:
                cat, sub = parts
                cands = []
                if cat == "ingots":
                    cands = [f"minecraft__{sub}_ingot.png", f"thermal__{sub}_ingot.png", f"mekanism__ingot_{sub}.png", f"pneumaticcraft__ingot_{sub}.png"]
                elif cat == "gems":
                    cands = [f"minecraft__{sub}.png", f"thermal__{sub}.png", f"mekanism__{sub}.png"]
                elif cat == "dusts":
                    cands = [f"minecraft__{sub}.png", f"thermal__{sub}_dust.png", f"mekanism__dust_{sub}.png"]
                elif cat == "storage_blocks":
                    cands = [f"minecraft__{sub}_block.png", f"thermal__{sub}_block.png", f"mekanism__block_{sub}.png"]
                elif cat == "dyes":
                    cands = [f"minecraft__{sub}_dye.png"]
                elif cat == "ores":
                    cands = [f"minecraft__{sub}_ore.png", f"thermal__{sub}_ore.png", f"minecraft__deepslate_{sub}_ore.png"]
                elif cat == "nuggets":
                    cands = [f"minecraft__{sub}_nugget.png", f"thermal__{sub}_nugget.png"]
                elif cat == "raw_materials":
                    cands = [f"minecraft__raw_{sub}.png", f"thermal__raw_{sub}.png"]
                elif cat == "crops":
                    cands = [f"minecraft__{sub}.png"]
                elif cat == "rods":
                    cands = [f"minecraft__{sub}_rod.png"]

                for c in cands:
                    if c in self._available_files:
                        return self.icons_dir / c

                for f in self._available_files:
                    if f.endswith(f"__{sub}.png") or f.endswith(f"__{sub}_ingot.png") or f.endswith(f"__ingot_{sub}.png") or f.endswith(f"__{sub}_dust.png"):
                        return self.icons_dir / f

            for f in self._available_files:
                if f.endswith(f"__{name_clean}.png"):
                    return self.icons_dir / f

        # 4. Machine suffixes check (_front, _side, _top, _north, _off, _controller, etc.)
        for suf in ("_front.png", "_side.png", "_top.png", "_north.png", "_x_off.png", "_off.png", "_controller.png", "_front_off.png", "_side_off.png"):
            f_suf = f"{ns}__{name_clean}{suf}"
            if f_suf in self._available_files:
                return self.icons_dir / f_suf

        # 5. Vanilla fallback
        fallback_mc = f"minecraft__{name_clean}.png"
        if fallback_mc in self._available_files:
            return self.icons_dir / fallback_mc

        return None

    def get_icon_bytes(self, raw_id: str) -> bytes:
        icon_path = self.get_icon_path(raw_id)
        if icon_path and icon_path.exists():
            try:
                return icon_path.read_bytes()
            except Exception:
                pass
        return _TRANSPARENT_1X1
