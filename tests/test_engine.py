"""Unit and integration tests for the Phase 3 Dependency Engine."""

from __future__ import annotations

from backend.engine.crafting import DependencyEngine
from backend.engine.models import NodeStatus
from backend.importer.tags import TagRegistry
from backend.models.recipe import (
    DataSource,
    IngredientSlot,
    MachineInfo,
    NormalizedRecipe,
    RecipeStack,
    ResourceType,
    ValidationStatus,
)


def _make_recipe(
    recipe_id: str,
    output_id: str,
    output_count: int,
    inputs: list[tuple[str, int, bool]],  # (resource_id, count, consumable)
    recipe_type: str = "minecraft:crafting_shaped",
    station_id: str = "minecraft:crafting_table",
    station_name: str = "Crafting Table",
) -> NormalizedRecipe:
    slots = []
    for in_id, count, consumable in inputs:
        is_tag = in_id.startswith("#")
        clean_id = in_id[1:] if is_tag else in_id
        r_type = ResourceType.TAG if is_tag else ResourceType.ITEM
        slots.append(
            IngredientSlot(
                alternatives=[RecipeStack(clean_id, 1, r_type)],
                count=count,
                consumable=consumable,
            )
        )
    return NormalizedRecipe(
        recipe_id=recipe_id,
        recipe_type=recipe_type,
        source_mod="test",
        data_source=DataSource.TEST_FIXTURE,
        source_path="fixtures/test.json",
        outputs=[RecipeStack(output_id, output_count)],
        inputs=slots,
        machine_info=MachineInfo(station_id=station_id, station_name=station_name),
        validation_status=ValidationStatus.VALID,
    )


def test_recursive_dependency_tree_expansion() -> None:
    """Test standard linear dependency expansion (Piston -> Iron, Wood Planks, Cobble, Redstone)."""
    recipes = {
        "oak_planks": _make_recipe("oak_planks", "minecraft:oak_planks", 4, [("minecraft:oak_log", 1, True)]),
        "stick": _make_recipe("stick", "minecraft:stick", 4, [("minecraft:oak_planks", 2, True)]),
        "iron_pickaxe": _make_recipe(
            "iron_pickaxe",
            "minecraft:iron_pickaxe",
            1,
            [("minecraft:iron_ingot", 3, True), ("minecraft:stick", 2, True)],
        ),
    }
    engine = DependencyEngine(recipes)

    # We want 1 iron pickaxe:
    # Requires 3 iron_ingot (raw) + 2 stick
    # 2 stick comes from 1 batch of stick (produces 4, needs 2 oak_planks)
    # 2 oak_planks comes from 1 batch of oak_planks (produces 4, needs 1 oak_log)
    tree = engine.build_crafting_tree("minecraft:iron_pickaxe", target_count=1)

    assert tree.target_item_key == "minecraft:iron_pickaxe"
    assert tree.root_node.status == NodeStatus.CRAFTABLE
    assert len(tree.steps) == 3
    assert not tree.has_circular_dependency

    # Check consolidated raw materials
    raw_mats = {m.resource_id: m.total_needed for m in tree.raw_materials}
    assert raw_mats["minecraft:iron_ingot"] == 3
    assert raw_mats["minecraft:oak_log"] == 1


def test_cycle_detection_without_infinite_recursion() -> None:
    """Test cycle detection (iron_block -> 9 iron_ingots -> iron_block) is safely flagged."""
    recipes = {
        "iron_block": _make_recipe(
            "iron_block", "minecraft:iron_block", 1, [("minecraft:iron_ingot", 9, True)]
        ),
        "iron_ingots_from_block": _make_recipe(
            "iron_ingots_from_block",
            "minecraft:iron_ingot",
            9,
            [("minecraft:iron_block", 1, True)],
            recipe_type="minecraft:crafting_shapeless",
        ),
    }
    engine = DependencyEngine(recipes)

    # Force selection of the reciprocal recipe to simulate intentional circular choice
    selected = {"minecraft:iron_ingot": "iron_ingots_from_block"}
    tree = engine.build_crafting_tree("minecraft:iron_block", 1, selected_recipes=selected)

    assert tree.has_circular_dependency is True
    cycle_nodes = [
        c
        for c in tree.root_node.children[0].children
        if c.status == NodeStatus.CIRCULAR_DEPENDENCY
    ]
    assert len(cycle_nodes) > 0
    assert cycle_nodes[0].item_key == "minecraft:iron_block"


def test_catalyst_non_consumed_not_multiplied() -> None:
    """Test non-consumed catalyst (e.g. Master Infusion Crystal, Press Die) is not multiplied across batches."""
    recipes = {
        "supremium_essence": _make_recipe(
            "supremium_essence",
            "mysticalagriculture:supremium_essence",
            1,
            [
                ("mysticalagriculture:imperium_essence", 4, True),
                ("mysticalagriculture:master_infusion_crystal", 1, False),  # Non-consumed catalyst!
            ],
        ),
    }
    engine = DependencyEngine(recipes)

    # Ask for 100 supremium essences:
    # Requires 100 * 4 = 400 imperium essences
    # BUT only 1 master_infusion_crystal!
    tree = engine.build_crafting_tree("mysticalagriculture:supremium_essence", 100)

    raw_mats = {m.resource_id: m.total_needed for m in tree.raw_materials}
    catalysts = {c.resource_id: c.total_needed for c in tree.catalysts}

    assert raw_mats["mysticalagriculture:imperium_essence"] == 400
    assert "mysticalagriculture:master_infusion_crystal" in catalysts
    assert catalysts["mysticalagriculture:master_infusion_crystal"] == 1


def test_alternative_recipe_selection() -> None:
    """Test user can pick alternative recipes (e.g. blast furnace vs normal furnace)."""
    recipes = {
        "iron_smelting": _make_recipe(
            "iron_smelting",
            "minecraft:iron_ingot",
            1,
            [("minecraft:raw_iron", 1, True)],
            recipe_type="minecraft:smelting",
        ),
        "iron_blasting": _make_recipe(
            "iron_blasting",
            "minecraft:iron_ingot",
            1,
            [("minecraft:raw_iron", 1, True)],
            recipe_type="minecraft:blasting",
            station_id="minecraft:blast_furnace",
            station_name="Blast Furnace",
        ),
    }
    engine = DependencyEngine(recipes)

    # Default heuristic picks first
    tree_default = engine.build_crafting_tree("minecraft:iron_ingot", 1)
    assert tree_default.root_node.status == NodeStatus.ALTERNATIVE_AVAILABLE
    assert len(tree_default.root_node.available_recipes) == 2

    # Override to blast furnace
    tree_custom = engine.build_crafting_tree(
        "minecraft:iron_ingot",
        1,
        selected_recipes={"minecraft:iron_ingot": "iron_blasting"},
    )
    assert tree_custom.root_node.selected_recipe.recipe_id in ("iron_blasting", "minecraft:iron_blasting")
    assert tree_custom.steps[0].recipe_id in ("iron_blasting", "minecraft:iron_blasting")


def test_tag_resolution_with_almost_unified() -> None:
    """Test tags in recipe ingredients resolve to preferred concrete item."""
    tag_reg = TagRegistry()
    tag_reg.add_tag_data(
        "forge:ingots/copper",
        {"replace": False, "values": ["mekanism:ingot_copper", "minecraft:copper_ingot"]},
    )
    # Minecraft has higher priority than mekanism in Almost Unified default
    assert tag_reg.get_preferred_item("forge:ingots/copper") == "minecraft:copper_ingot"

    recipes = {
        "copper_block": _make_recipe(
            "copper_block", "minecraft:copper_block", 1, [("#forge:ingots/copper", 9, True)]
        ),
    }
    engine = DependencyEngine(recipes, tag_registry=tag_reg)

    tree = engine.build_crafting_tree("minecraft:copper_block", 1)
    # The child node resolved from the tag should be the preferred item: minecraft:copper_ingot
    child = tree.root_node.children[0]
    assert child.resource_id == "minecraft:copper_ingot"
    assert child.count == 9


def test_prune_basic_resources_and_avoid_uncompressing() -> None:
    """Test that basic resources (logs, cobblestone, ores) are pruned to raw leaves and uncompressing is avoided."""
    recipes = {
        # Uncompressing loop that shouldn't be picked as primary
        "compressium_cobble": _make_recipe(
            "compressium:cobblestone_1_uncraft",
            "minecraft:cobblestone",
            9,
            [("compressium:cobblestone_1", 1, True)],
            recipe_type="minecraft:crafting_shapeless",
        ),
        # Real cobblestone recipe (e.g. from stones or generators)
        "stone_to_cobble": _make_recipe(
            "stone_to_cobble",
            "minecraft:cobblestone",
            1,
            [("minecraft:stone", 1, True)],
        ),
        # Piston needing cobblestone, planks, iron and redstone
        "piston": _make_recipe(
            "piston",
            "minecraft:piston",
            1,
            [
                ("minecraft:oak_planks", 3, True),
                ("minecraft:cobblestone", 4, True),
                ("minecraft:iron_ingot", 1, True),
                ("minecraft:redstone", 1, True),
            ],
        ),
        "oak_planks": _make_recipe(
            "oak_planks",
            "minecraft:oak_planks",
            4,
            [("minecraft:oak_log", 1, True)],
        ),
    }
    engine = DependencyEngine(recipes)

    # 1. With pruning enabled (default):
    # Cobblestone and Redstone are basic raw resources -> they stop expanding and become RAW_MATERIAL leaves.
    # Oak planks expand to oak_log, which is a basic raw resource and stops there.
    tree = engine.build_crafting_tree("minecraft:piston", 1, prune_basic=True)
    raw_mats = {m.resource_id: m.total_needed for m in tree.raw_materials}

    assert "minecraft:cobblestone" in raw_mats
    assert raw_mats["minecraft:cobblestone"] == 4
    assert "minecraft:redstone" in raw_mats
    assert raw_mats["minecraft:redstone"] == 1
    assert "minecraft:oak_log" in raw_mats
    assert "compressium:cobblestone_1" not in raw_mats
    assert not tree.has_circular_dependency

    # 2. When the basic item itself is the root search target, it is not pruned:
    tree_cobble = engine.build_crafting_tree("minecraft:cobblestone", 1, prune_basic=True)
    assert tree_cobble.root_node.status != NodeStatus.RAW_MATERIAL


def test_compressium_excluded_from_base_tree_but_kept_for_advanced() -> None:
    """Verify that compressium is rejected as a shortcut for simple items but preserved in advanced recipes."""
    recipes = {
        # Extreme shortcut: 344k compressed coal to make an item (like hellforged parts)
        "bad_bulk_recipe": _make_recipe(
            "mm:coal_to_hellforged_parts",
            "bloodmagic:hellforgedparts",
            1,
            [("compressium:coal_2", 344064, True)],
            recipe_type="mm:process",
        ),
        # Advanced recipe explicitly requiring compressium (e.g. Cyclic user)
        "advanced_cyclic_user": _make_recipe(
            "cyclic:user",
            "cyclic:user",
            1,
            [("compressium:cobblestone_1", 1, True), ("minecraft:gold_ingot", 2, True)],
        ),
    }
    engine = DependencyEngine(recipes)

    # 1. Simple item having only a bulk compressium recipe:
    # The bulk compressium recipe is rejected -> item is treated as RAW_MATERIAL (dungeon loot / mob drop)
    tree_hell = engine.build_crafting_tree("bloodmagic:hellforgedparts", 1, prune_basic=True)
    assert tree_hell.root_node.status == NodeStatus.RAW_MATERIAL
    raw_mats_hell = {m.resource_id: m.total_needed for m in tree_hell.raw_materials}
    assert "bloodmagic:hellforgedparts" in raw_mats_hell
    assert "minecraft:coal" not in raw_mats_hell
    assert "compressium:coal_2" not in raw_mats_hell

    # 2. Advanced item explicitly requiring compressium:
    # compressium:cobblestone_1 is kept in the tree as the required advanced component
    tree_cyclic = engine.build_crafting_tree("cyclic:user", 1, prune_basic=True)
    assert len(tree_cyclic.steps) == 1
    raw_mats_cyclic = {m.resource_id: m.total_needed for m in tree_cyclic.raw_materials}
    assert "compressium:cobblestone_1" in raw_mats_cyclic
    assert raw_mats_cyclic["compressium:cobblestone_1"] == 1


def test_mystical_agriculture_avoided_for_powah_and_tech() -> None:
    """Verify that cross-mod essence crafting is avoided in favor of native machines like Powah Energizing Orb."""
    rec_ma = _make_recipe(
        "mysticalagriculture:essence/powah/blazing_crystal",
        "powah:crystal_blazing",
        1,
        [("mysticalagriculture:blazing_crystal_essence", 8, True)],
        recipe_type="cucumber:shaped_no_mirror",
        station_id="minecraft:crafting_table",
        station_name="Crafting Table",
    )
    rec_ma.source_mod = "mysticalagriculture"

    rec_powah = _make_recipe(
        "powah:energizing/blazing_crystal",
        "powah:crystal_blazing",
        1,
        [("minecraft:blaze_rod", 1, True)],
        recipe_type="powah:energizing",
        station_id="powah:energizing_orb",
        station_name="Energizing Orb",
    )
    rec_powah.source_mod = "powah"

    engine = DependencyEngine({
        "ma_blazing": rec_ma,
        "powah_blazing": rec_powah,
    })

    # With avoid_mystical_agriculture=True (default), Energizing Orb must be chosen!
    tree = engine.build_crafting_tree("powah:crystal_blazing", 1, avoid_mystical_agriculture=True)
    assert tree.root_node.selected_recipe is not None
    assert tree.root_node.selected_recipe.recipe_id == "powah:energizing/blazing_crystal"
    assert tree.root_node.selected_recipe.machine_info.station_id == "powah:energizing_orb"
    assert tree.root_node.selected_recipe.machine_info.station_name == "Energizing Orb"
    assert tree.steps[0].machine_name == "Energizing Orb"

    # When avoid_mystical_agriculture=False, if user explicitly disables the lock, MA can be picked
    tree_ma = engine.build_crafting_tree("powah:crystal_blazing", 1, avoid_mystical_agriculture=False)
    assert tree_ma.root_node.selected_recipe is not None


