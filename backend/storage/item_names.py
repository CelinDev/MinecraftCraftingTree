"""Item name resolution and formatting service using extracted Minecraft and mod language files."""

from __future__ import annotations

import json
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
ITEM_NAMES_PATH = ROOT_DIR / "data" / "item_names.json"

MOD_NAMES: dict[str, str] = {
    "minecraft": "Minecraft",
    "powah": "Powah!",
    "mekanism": "Mekanism",
    "thermal": "Thermal Series",
    "enderio": "Ender IO",
    "botania": "Botania",
    "bloodmagic": "Blood Magic",
    "nuclearcraft": "NuclearCraft",
    "actuallyadditions": "Actually Additions",
    "extendedcrafting": "Extended Crafting",
    "avaritia": "Avaritia",
    "cyclic": "Cyclic",
    "mysticalagriculture": "Mystical Agriculture",
    "mysticalagradditions": "Mystical Agradditions",
    "ae2": "Applied Energistics 2",
    "exdeorum": "Ex Deorum",
    "hostilenetworks": "Hostile Neural Networks",
    "integrateddynamics": "Integrated Dynamics",
    "tconstruct": "Tinkers' Construct",
    "draconicevolution": "Draconic Evolution",
    "kubejs": "KubeJS",
    "sophisticatedstorage": "Sophisticated Storage",
    "sophisticatedbackpacks": "Sophisticated Backpacks",
    "botanypots": "Botany Pots",
    "pneumaticcraft": "PneumaticCraft",
    "compressium": "Compressium",
    "allthemodium": "Allthemodium",
    "industrialforegoing": "Industrial Foregoing",
}


class ItemNameService:
    """Provides high-speed translated names and formatters for all modpack items and blocks."""

    def __init__(self, json_path: Path = ITEM_NAMES_PATH) -> None:
        self.json_path = json_path
        self._names: dict[str, str] = {}
        self.reload()

    def reload(self) -> None:
        if self.json_path.exists():
            try:
                with open(self.json_path, "r", encoding="utf-8") as f:
                    self._names = json.load(f)
            except Exception:
                self._names = {}

    def get_display_name(self, raw_id: str | None) -> str:
        if not raw_id:
            return ""
        clean = str(raw_id).strip()
        is_tag = clean.startswith("#")
        if is_tag:
            clean = clean[1:]

        # 1. Exact match in translations
        if clean in self._names:
            name = self._names[clean]
            return f"#{name}" if is_tag else name

        # 2. Namespace:item check
        if ":" in clean:
            ns, item = clean.split(":", 1)
            # Remove NBT or compound brackets
            item_clean = item.split("{")[0]
            clean_key = f"{ns}:{item_clean}"
            if clean_key in self._names:
                name = self._names[clean_key]
                return f"#{name}" if is_tag else name

            # 3. Format forge tag: forge:ingots/iron -> "Iron Ingot (Tag)"
            if is_tag or ns == "forge":
                sub = item_clean.split("/")[-1].replace("_", " ").title()
                cat = item_clean.split("/")[0].replace("_", " ").title() if "/" in item_clean else ""
                if cat and cat != sub:
                    return f"{sub} ({cat})"
                return f"{sub} (Tag)"

            # 4. Fallback: Title case of item name
            return item_clean.replace("_", " ").title()

        return clean.replace("_", " ").title()

    def format_mod_name(self, mod_id: str | None) -> str:
        if not mod_id:
            return ""
        clean = str(mod_id).strip().lower()
        return MOD_NAMES.get(clean, clean.replace("_", " ").title())


item_names = ItemNameService()

