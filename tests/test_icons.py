"""Tests for FastStaticIconService: Forge tag and machine icon resolution."""

from __future__ import annotations

from backend.storage.fast_icons import FastStaticIconService


def test_forge_tags_and_machines_resolve_to_real_icons() -> None:
    service = FastStaticIconService()

    # 1. Forge tags
    test_tags = [
        "forge:gems/diamond",
        "#forge:gems/diamond",
        "forge:ingots/iron",
        "forge:ingots/gold",
        "forge:dusts/redstone",
        "forge:rods/wooden",
        "forge:storage_blocks/iron",
        "forge:obsidian",
    ]
    for tag in test_tags:
        icon_path = service.get_icon_path(tag)
        assert icon_path is not None, f"Expected icon path for tag {tag}"
        assert icon_path.exists(), f"Icon file {icon_path} should exist on disk"
        data = service.get_icon_bytes(tag)
        assert len(data) > 100, f"Icon for {tag} should not be transparent 1x1 placeholder"

    # 2. Machines and Crafting Stations
    test_machines = [
        "minecraft:crafting_table",
        "minecraft:furnace",
        "minecraft:blast_furnace",
        "thermal:machine_press",
        "mekanism:crusher",
        "botanypots:terracotta_botany_pot",
        "exdeorum:oak_sieve",
        "extendedcrafting:compressor",
    ]
    for machine in test_machines:
        icon_path = service.get_icon_path(machine)
        assert icon_path is not None, f"Expected icon path for machine {machine}"
        assert icon_path.exists(), f"Icon file {icon_path} should exist on disk"
        data = service.get_icon_bytes(machine)
        assert len(data) > 100, f"Icon for {machine} should not be transparent 1x1 placeholder"

