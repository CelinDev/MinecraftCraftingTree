"""Automated tests for the Phase 2 Recipe Importer using explicit TEST_FIXTURE data."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

from backend.importer.adapters import parse_recipe_json
from backend.importer.kubejs_processor import (
    parse_kubejs_server_scripts,
    parse_masterful_machinery_processes,
)
from backend.importer.pipeline import ModpackImporter
from backend.importer.tags import TagRegistry
from backend.models.recipe import (
    DataSource,
    NormalizedRecipe,
    ResourceType,
    ValidationStatus,
)


def test_parse_valid_shaped_and_shapeless_recipes() -> None:
    """Verify reading of valid shaped and shapeless recipes and quantity aggregation."""
    shaped_fixture = {
        "type": "minecraft:crafting_shaped",
        "pattern": ["III", " S ", " S "],
        "key": {
            "I": {"item": "minecraft:iron_ingot"},
            "S": {"tag": "forge:rods/wooden"},
        },
        "result": {"item": "minecraft:iron_pickaxe", "count": 1},
    }
    rec, skipped = parse_recipe_json(
        recipe_id="test_fixture:iron_pickaxe",
        data=shaped_fixture,
        data_source=DataSource.TEST_FIXTURE,
        source_path="fixtures/iron_pickaxe.json",
    )
    assert not skipped
    assert rec is not None
    assert rec.validation_status == ValidationStatus.VALID
    assert rec.output_item_id == "minecraft:iron_pickaxe"
    assert rec.output_count == 1
    assert len(rec.inputs) == 2

    iron_slot = next(s for s in rec.inputs if s.slot_key == "I")
    assert iron_slot.count == 3
    assert iron_slot.alternatives[0].resource_id == "minecraft:iron_ingot"
    assert iron_slot.alternatives[0].resource_type == ResourceType.ITEM

    stick_slot = next(s for s in rec.inputs if s.slot_key == "S")
    assert stick_slot.count == 2
    assert stick_slot.alternatives[0].resource_id == "forge:rods/wooden"
    assert stick_slot.alternatives[0].resource_type == ResourceType.TAG


def test_handle_invalid_and_empty_recipe_files() -> None:
    """Verify treatment of invalid/malformed JSON objects and empty override JSONs ({})."""
    # 1. Non-dict payload
    rec_invalid, _ = parse_recipe_json(
        recipe_id="test_fixture:broken_list",
        data=["not", "a", "dict"],
        data_source=DataSource.TEST_FIXTURE,
        source_path="fixtures/broken.json",
    )
    assert rec_invalid is not None
    assert rec_invalid.validation_status == ValidationStatus.INVALID
    assert rec_invalid.raw_data == ["not", "a", "dict"]

    # 2. Missing 'type' field
    rec_no_type, _ = parse_recipe_json(
        recipe_id="test_fixture:missing_type",
        data={"result": "minecraft:stone"},
        data_source=DataSource.TEST_FIXTURE,
        source_path="fixtures/missing_type.json",
    )
    assert rec_no_type is not None
    assert rec_no_type.validation_status == ValidationStatus.INVALID
    assert rec_no_type.raw_data == {"result": "minecraft:stone"}

    # 3. Empty dict {} used by KubeJS datapacks to disable a recipe
    rec_empty, _ = parse_recipe_json(
        recipe_id="test_fixture:disabled_recipe",
        data={},
        data_source=DataSource.TEST_FIXTURE,
        source_path="fixtures/disabled.json",
    )
    assert rec_empty is not None
    assert rec_empty.validation_status == ValidationStatus.REMOVED


def test_alternative_ingredients_in_slot() -> None:
    """Verify handling of alternative ingredients (arrays of items/tags in a single slot)."""
    fixture = {
        "type": "minecraft:crafting_shapeless",
        "ingredients": [
            [
                {"item": "minecraft:coal"},
                {"item": "minecraft:charcoal"},
                {"tag": "forge:coal_coke"},
            ],
            {"item": "minecraft:stick"},
        ],
        "result": {"item": "minecraft:torch", "count": 4},
    }
    rec, _ = parse_recipe_json(
        recipe_id="test_fixture:torch_alternatives",
        data=fixture,
        data_source=DataSource.TEST_FIXTURE,
        source_path="fixtures/torch.json",
    )
    assert rec is not None
    assert rec.validation_status == ValidationStatus.VALID
    assert rec.output_count == 4
    assert len(rec.inputs) == 2

    coal_slot = rec.inputs[0]
    assert len(coal_slot.alternatives) == 3
    alt_ids = [a.item_key for a in coal_slot.alternatives]
    assert alt_ids == ["minecraft:coal", "minecraft:charcoal", "#forge:coal_coke"]


def test_multiple_outputs_and_fluid_gas_resources() -> None:
    """Verify identification of multiple outputs (primary + secondary + gas/fluid) and probabilities."""
    prc_fixture = {
        "type": "mekanism:reaction",
        "itemInput": {"ingredient": {"tag": "forge:fuels/bio"}, "amount": 2},
        "fluidInput": {"fluid": "minecraft:water", "amount": 10},
        "gasInput": {"gas": "mekanism:hydrogen", "amount": 100},
        "itemOutput": {"item": "mekanism:substrate", "count": 1},
        "gasOutput": {"gas": "mekanism:ethene", "amount": 100},
        "duration": 100,
    }
    rec, _ = parse_recipe_json(
        recipe_id="test_fixture:prc_substrate",
        data=prc_fixture,
        data_source=DataSource.TEST_FIXTURE,
        source_path="fixtures/prc.json",
    )
    assert rec is not None
    assert rec.validation_status == ValidationStatus.VALID
    assert len(rec.inputs) == 3
    assert len(rec.outputs) == 2

    primary_out = rec.primary_output
    assert primary_out is not None
    assert primary_out.resource_id == "mekanism:substrate"
    assert primary_out.resource_type == ResourceType.ITEM

    secondary_out = rec.outputs[1]
    assert secondary_out.resource_id == "mekanism:ethene"
    assert secondary_out.resource_type == ResourceType.GAS
    assert secondary_out.count == 100
    assert not secondary_out.is_primary


def test_preserve_unsupported_recipe_raw_data() -> None:
    """Verify preservation of original raw_data when a recipe is dynamic or unsupported."""
    special_fixture = {
        "type": "minecraft:crafting_special_armordye",
        "category": "misc",
    }
    rec, _ = parse_recipe_json(
        recipe_id="minecraft:armor_dye",
        data=special_fixture,
        data_source=DataSource.TEST_FIXTURE,
        source_path="fixtures/armor_dye.json",
    )
    assert rec is not None
    assert rec.validation_status == ValidationStatus.UNSUPPORTED
    assert rec.raw_data == special_fixture
    assert len(rec.warnings) > 0


def test_masterful_machinery_catalyst_and_nbt_parsing() -> None:
    """Verify Masterful Machinery JS process parsing, non-consumed catalyst (chance: 0.0), and NBT."""
    mm_js = """
    MMEvents.createProcesses((event) => {
      event
        .create('mm:test_crucible_recipe')
        .structureId('mm:infinity_crucible_structure')
        .ticks(20)
        .input({
          type: 'mm:input/consume',
          chance: 0.0,
          ingredient: {
            type: 'mm:item',
            item: 'kubejs:ultimate_heart',
            count: 1,
          },
        })
        .input({
          type: 'mm:input/consume',
          ingredient: {
            type: 'mm:mekanism/gas',
            gas: 'mekanism:antimatter',
            amount: 5,
          },
        })
        .input({
          type: 'mm:input/consume',
          ingredient: {
            type: 'mm:energy',
            amount: 50000,
          },
        })
        .output({
          type: 'mm:output/simple',
          ingredient: {
            type: 'mm:item',
            item: 'draconicevolution:chaos_shard',
            count: 4,
          },
        });
    });
    """
    recipes = parse_masterful_machinery_processes(mm_js, "fixtures/mm_test.js")
    assert len(recipes) == 1
    rec = recipes[0]
    assert rec.recipe_id == "mm:test_crucible_recipe"
    assert rec.validation_status == ValidationStatus.VALID
    assert rec.output_item_id == "draconicevolution:chaos_shard"
    assert rec.output_count == 4
    assert rec.machine_info is not None
    assert rec.machine_info.energy_fe == 50000
    assert rec.machine_info.ticks == 20

    heart_slot = next(s for s in rec.inputs if s.alternatives[0].resource_id == "kubejs:ultimate_heart")
    assert heart_slot.chance == 0.0
    assert heart_slot.consumable is False

    gas_slot = next(s for s in rec.inputs if s.alternatives[0].resource_id == "mekanism:antimatter")
    assert gas_slot.alternatives[0].resource_type == ResourceType.GAS
    assert gas_slot.count == 5
    assert gas_slot.consumable is True


def test_duplicate_detection_and_layered_pipeline(tmp_path: Path) -> None:
    """Verify duplicate override detection, datapack `{}` removal, KubeJS removals, and replaceInput."""
    inst_dir = tmp_path / "TestInstance"
    mods_dir = inst_dir / "mods"
    kube_data_dir = inst_dir / "kubejs" / "data" / "testmod" / "recipes"
    kube_scripts_dir = inst_dir / "kubejs" / "server_scripts"
    mods_dir.mkdir(parents=True)
    kube_data_dir.mkdir(parents=True)
    kube_scripts_dir.mkdir(parents=True)

    (inst_dir / "manifest.json").write_text(
        json.dumps(
            {
                "name": "Fixture Pack",
                "version": "1.0.0",
                "minecraft": {"version": "1.20.1", "modLoaders": [{"id": "forge-47.4.28"}]},
            }
        ),
        encoding="utf-8",
    )

    # Create a synthetic mod JAR with 3 recipes (1 to keep+override, 1 to disable via {}, 1 to remove via KubeJS)
    jar_path = mods_dir / "testmod-1.0.jar"
    with zipfile.ZipFile(jar_path, "w") as zf:
        zf.writestr('META-INF/mods.toml', 'modId="testmod"\n')
        zf.writestr(
            "data/testmod/recipes/overridden_item.json",
            json.dumps(
                {
                    "type": "minecraft:crafting_shapeless",
                    "ingredients": [{"item": "minecraft:dirt"}],
                    "result": {"item": "testmod:overridden_item", "count": 1},
                }
            ),
        )
        zf.writestr(
            "data/testmod/recipes/empty_removed_item.json",
            json.dumps(
                {
                    "type": "minecraft:crafting_shapeless",
                    "ingredients": [{"item": "minecraft:cobblestone"}],
                    "result": {"item": "testmod:empty_removed_item", "count": 1},
                }
            ),
        )
        zf.writestr(
            "data/testmod/recipes/script_removed_item.json",
            json.dumps(
                {
                    "type": "minecraft:crafting_shapeless",
                    "ingredients": [{"item": "minecraft:sand"}],
                    "result": {"item": "testmod:script_removed_item", "count": 1},
                }
            ),
        )

    # Override `testmod:overridden_item` in kubejs/data and disable `testmod:empty_removed_item` with `{}`
    (kube_data_dir / "overridden_item.json").write_text(
        json.dumps(
            {
                "type": "minecraft:crafting_shapeless",
                "ingredients": [{"item": "minecraft:diamond"}],
                "result": {"item": "testmod:overridden_item", "count": 2},
            }
        ),
        encoding="utf-8",
    )
    (kube_data_dir / "empty_removed_item.json").write_text("{}", encoding="utf-8")

    # Add KubeJS script that removes `testmod:script_removed_item`, replaces diamond -> emerald, and adds a 3x3 helper recipe
    (kube_scripts_dir / "test_changes.js").write_text(
        """
        const removeRecipebyOutput = ['testmod:script_removed_item'];
        ServerEvents.recipes((event) => {
          removeRecipebyOutput.forEach((item) => event.remove({ output: item }));
          event.replaceInput(
            { output: 'testmod:overridden_item' },
            'minecraft:diamond',
            'minecraft:emerald'
          );
          create3x3same(event, 'testmod:compressed_emerald', ['minecraft:emerald']);
        });
        """,
        encoding="utf-8",
    )

    importer = ModpackImporter(inst_dir)
    result = importer.run(load_tags=True)

    assert result.report is not None
    # 1. Duplicate override recorded for `testmod:overridden_item`
    assert result.report.overridden_Duplicates_count == 1
    overridden = result.recipes["testmod:overridden_item"]
    assert overridden.output_count == 2
    # And its input was replaced from minecraft:diamond to minecraft:emerald!
    assert overridden.inputs[0].alternatives[0].resource_id == "minecraft:emerald"

    # 2. Both removed recipes are in removed_recipes and NOT in active recipes
    assert "testmod:empty_removed_item" not in result.recipes
    assert "testmod:empty_removed_item" in result.removed_recipes
    assert "testmod:script_removed_item" not in result.recipes
    assert "testmod:script_removed_item" in result.removed_recipes

    # 3. KubeJS helper recipe was added and normalized
    compressed_matches = result.get_recipes_for_output("testmod:compressed_emerald")
    assert len(compressed_matches) == 1
    assert compressed_matches[0].inputs[0].count == 9
    assert compressed_matches[0].inputs[0].alternatives[0].resource_id == "minecraft:emerald"


def test_tag_unification_priority() -> None:
    """Verify Almost Unified tag resolution order."""
    reg = TagRegistry()
    reg.add_tag_data(
        "forge:ingots/steel",
        {
            "replace": False,
            "values": [
                "nuclearcraft:steel_ingot",
                "mekanism:ingot_steel",
                "thermal:steel_ingot",
            ],
        },
    )
    # Default priority: minecraft > kubejs > thermal > mekanism > common_ore_library
    assert reg.get_preferred_item("forge:ingots/steel") == "thermal:steel_ingot"
    assert reg.get_tag_items("forge:ingots/steel") == [
        "thermal:steel_ingot",
        "mekanism:ingot_steel",
        "nuclearcraft:steel_ingot",
    ]

