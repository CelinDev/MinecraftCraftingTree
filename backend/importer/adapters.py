"""Adapters for interpreting and normalizing Minecraft and Modpack recipe JSON formats."""

from __future__ import annotations

from typing import Any

from backend.importer.tags import TagRegistry
from backend.models.recipe import (
    DataSource,
    IngredientSlot,
    MachineInfo,
    NormalizedRecipe,
    RecipeStack,
    ResourceType,
    ValidationStatus,
    canonicalize_nbt,
    normalize_identifier,
)

# Known special/code-driven recipe types that have no static ingredient/result graph
SPECIAL_DYNAMIC_RECIPE_TYPES: set[str] = {
    "minecraft:crafting_special_armordye",
    "minecraft:crafting_special_bookcloning",
    "minecraft:crafting_special_mapcloning",
    "minecraft:crafting_special_mapextending",
    "minecraft:crafting_special_firework_rocket",
    "minecraft:crafting_special_firework_star",
    "minecraft:crafting_special_firework_star_fade",
    "minecraft:crafting_special_tippedarrow",
    "minecraft:crafting_special_bannerduplicate",
    "minecraft:crafting_special_shielddecoration",
    "minecraft:crafting_special_shulkerboxcoloring",
    "minecraft:crafting_special_suspiciousstew",
    "minecraft:crafting_special_repairitem",
    "minecraft:smithing_trim",
    "ae2:facade",
    "cable_facades:facade",
    "mekanism:bin_insert",
    "mekanism:bin_extract",
}

# Known non-consumed catalyst items (e.g. Thermal press dies, Mystical Agriculture infusion crystals)
NON_CONSUMED_ITEMS: set[str] = {
    "mysticalagriculture:master_infusion_crystal",
    "mysticalagriculture:infusion_crystal",
    "kubejs:fake_philosophers_stone",
    "projecte:philosophers_stone",
    "bloodmagic:activationcrystalweak",
    "bloodmagic:activationcrystalawakened",
}


def is_non_consumed_item(item_id: str) -> bool:
    """Determine if an item ID acts as a non-consumed catalyst or mold."""
    norm = normalize_identifier(item_id)
    if norm in NON_CONSUMED_ITEMS:
        return True
    if norm.startswith("thermal:press_") and norm.endswith("_die"):
        return True
    return False


def evaluate_condition(
    cond: dict[str, Any],
    loaded_mods: set[str],
    tag_registry: TagRegistry | None = None,
) -> bool:
    """Evaluate a Forge / Bookshelf condition object."""
    if not isinstance(cond, dict):
        return True
    c_type = normalize_identifier(str(cond.get("type", "")))

    if c_type == "forge:mod_loaded":
        mod_id = str(cond.get("modid", cond.get("mod", ""))).strip()
        return mod_id in loaded_mods if loaded_mods else True

    if c_type == "forge:not":
        inner = cond.get("value")
        if isinstance(inner, dict):
            return not evaluate_condition(inner, loaded_mods, tag_registry)
        return True

    if c_type == "forge:and":
        values = cond.get("values", [])
        if isinstance(values, list):
            return all(evaluate_condition(v, loaded_mods, tag_registry) for v in values)
        return True

    if c_type == "forge:or":
        values = cond.get("values", [])
        if isinstance(values, list):
            return any(evaluate_condition(v, loaded_mods, tag_registry) for v in values)
        return True

    if c_type == "forge:false":
        return False

    if c_type == "forge:true":
        return True

    if c_type == "forge:tag_empty":
        tag_name = str(cond.get("tag", "")).strip()
        if tag_registry and tag_name:
            items = tag_registry.get_tag_items(tag_name)
            return len(items) == 0
        return False

    # Default permissive for mod-specific flags (e.g. bookshelf:item_exists, thermal:flag)
    return True


def evaluate_conditions_list(
    conditions: list[Any] | None,
    loaded_mods: set[str],
    tag_registry: TagRegistry | None = None,
) -> bool:
    """Evaluate a list of Forge conditions (ANDed together)."""
    if not conditions or not isinstance(conditions, list):
        return True
    return all(
        evaluate_condition(c, loaded_mods, tag_registry)
        for c in conditions
        if isinstance(c, dict)
    )


def parse_stack_Entry(
    obj: Any,
    default_type: ResourceType = ResourceType.ITEM,
) -> list[RecipeStack]:
    """Parse an arbitrary JSON ingredient or output entry into one or more RecipeStack objects."""
    if obj is None:
        return []

    if isinstance(obj, str):
        cleaned = obj.strip()
        if not cleaned or cleaned == "minecraft:air":
            return []
        count = 1
        # Support KubeJS shorthand like '9x kubejs:infinity_6'
        if "x " in cleaned and cleaned.split("x ", 1)[0].isdigit():
            cnt_str, item_part = cleaned.split("x ", 1)
            count = int(cnt_str)
            cleaned = item_part.strip()
        if cleaned.startswith("#"):
            return [RecipeStack(resource_id=cleaned[1:], count=count, resource_type=ResourceType.TAG)]
        return [RecipeStack(resource_id=cleaned, count=count, resource_type=default_type)]

    if isinstance(obj, list):
        stacks: list[RecipeStack] = []
        for elem in obj:
            stacks.extend(parse_stack_Entry(elem, default_type=default_type))
        return stacks

    if not isinstance(obj, dict):
        return []

    # Handle wrapped ingredient key (e.g. {"ingredient": {...}, "count": 4, "chance": 0.5})
    count: float | int = obj.get(
        "count",
        obj.get("amount", obj.get("Count", obj.get("materialCount", 1))),
    )
    chance = float(obj.get("chance", 1.0))
    nbt = obj.get("nbt", obj.get("nbt_snbt"))

    if "ingredient" in obj and isinstance(obj["ingredient"], (dict, list, str)):
        inner_stacks = parse_stack_Entry(obj["ingredient"], default_type=default_type)
        for st in inner_stacks:
            if count != 1 and st.count == 1:
                st.count = count
            if chance != 1.0:
                st.chance = chance
            if nbt and not st.nbt:
                st.nbt = canonicalize_nbt(nbt)
        return inner_stacks

    if "value" in obj and isinstance(obj["value"], (dict, list)):
        inner_stacks = parse_stack_Entry(obj["value"], default_type=default_type)
        for st in inner_stacks:
            if count != 1 and st.count == 1:
                st.count = count
        return inner_stacks

    if "base_ingredient" in obj:
        inner_stacks = parse_stack_Entry(obj["base_ingredient"], default_type=default_type)
        for st in inner_stacks:
            st.count = count
        return inner_stacks

    if "items" in obj and isinstance(obj["items"], list):
        inner_stacks = parse_stack_Entry(obj["items"], default_type=default_type)
        for st in inner_stacks:
            if count != 1 and st.count == 1:
                st.count = count
        return inner_stacks

    # Direct item / block / result keys
    for item_key in ("item", "id", "result", "output", "block", "seed", "crop"):
        if item_key in obj and isinstance(obj[item_key], str):
            raw_id = obj[item_key].strip()
            if not raw_id or raw_id == "minecraft:air":
                return []
            return [
                RecipeStack(
                    resource_id=raw_id,
                    count=count,
                    resource_type=ResourceType.TAG if raw_id.startswith("#") else default_type,
                    nbt=nbt,
                    chance=chance,
                )
            ]
        elif item_key in obj and isinstance(obj[item_key], dict):
            inner_stacks = parse_stack_Entry(obj[item_key], default_type=default_type)
            for st in inner_stacks:
                if count != 1 and st.count == 1:
                    st.count = count
                if chance != 1.0 and st.chance == 1.0:
                    st.chance = chance
            return inner_stacks

    # Tag keys
    if "tag" in obj and isinstance(obj["tag"], str):
        raw_tag = obj["tag"].strip().lstrip("#")
        r_type = ResourceType.FLUID_TAG if default_type == ResourceType.FLUID else ResourceType.TAG
        if "fluid" in obj or obj.get("type") in ("mm:fluid", "pneumaticcraft:fluid"):
            r_type = ResourceType.FLUID_TAG
        return [
            RecipeStack(
                resource_id=raw_tag,
                count=count,
                resource_type=r_type,
                nbt=nbt,
                chance=chance,
            )
        ]

    # Fluid keys
    for fluid_key in ("fluid", "FluidName"):
        if fluid_key in obj and isinstance(obj[fluid_key], str):
            return [
                RecipeStack(
                    resource_id=obj[fluid_key],
                    count=count,
                    resource_type=ResourceType.FLUID,
                    nbt=nbt,
                    chance=chance,
                )
            ]
        elif fluid_key in obj and isinstance(obj[fluid_key], dict):
            return parse_stack_Entry(obj[fluid_key], default_type=ResourceType.FLUID)

    if "fluidTag" in obj and isinstance(obj["fluidTag"], str):
        return [
            RecipeStack(
                resource_id=obj["fluidTag"],
                count=count,
                resource_type=ResourceType.FLUID_TAG,
                chance=chance,
            )
        ]

    # Mekanism gas / chemical / infuse_type / slurry / pigment keys
    for chem_key in ("gas", "chemical", "infuse_type", "pigment", "slurry"):
        if chem_key in obj and isinstance(obj[chem_key], str):
            return [
                RecipeStack(
                    resource_id=obj[chem_key],
                    count=count,
                    resource_type=ResourceType.GAS,
                    chance=chance,
                )
            ]
        elif chem_key in obj and isinstance(obj[chem_key], dict):
            return parse_stack_Entry(obj[chem_key], default_type=ResourceType.GAS)

    # Energy keys (e.g. Masterful Machinery {"type": "mm:energy", "amount": 200000})
    if obj.get("type") in ("mm:energy", "forge:energy") or ("energy" in obj and len(obj) == 1):
        e_val = obj.get("amount", obj.get("energy", count))
        return [
            RecipeStack(
                resource_id="forge:fe",
                count=e_val,
                resource_type=ResourceType.ENERGY,
                chance=chance,
            )
        ]

    return []


def build_slot(
    obj: Any,
    slot_key: str | None = None,
    default_type: ResourceType = ResourceType.ITEM,
    consumable: bool | None = None,
) -> IngredientSlot | None:
    """Construct an IngredientSlot from a raw JSON ingredient definition."""
    stacks = parse_stack_Entry(obj, default_type=default_type)
    if not stacks:
        return None

    chance = 1.0
    if isinstance(obj, dict) and "chance" in obj:
        chance = float(obj["chance"])
    else:
        chance = stacks[0].chance

    slot_count = stacks[0].count
    for st in stacks:
        st.count = 1  # Slot holds the count, alternatives hold unit references

    if consumable is None:
        if chance == 0.0:
            consumable = False
        elif len(stacks) == 1 and is_non_consumed_item(stacks[0].resource_id):
            consumable = False
        else:
            consumable = True

    return IngredientSlot(
        alternatives=stacks,
        count=slot_count,
        consumable=consumable,
        chance=chance,
        slot_key=slot_key,
    )


def _extract_shaped_inputs(
    pattern: list[str],
    key_map: dict[str, Any],
) -> list[IngredientSlot]:
    """Count symbol frequencies in a shaped pattern (3x3, 5x5, 7x7, 9x9) and aggregate slots."""
    symbol_counts: dict[str, int] = {}
    for row in pattern:
        if not isinstance(row, str):
            continue
        for ch in row:
            if ch != " ":
                symbol_counts[ch] = symbol_counts.get(ch, 0) + 1

    slots: list[IngredientSlot] = []
    for sym, freq in symbol_counts.items():
        if sym not in key_map:
            continue
        slot = build_slot(key_map[sym], slot_key=sym)
        if slot:
            slot.count = slot.count * freq
            slots.append(slot)
    return slots


def _infer_machine_info(recipe_type: str, data: dict[str, Any]) -> MachineInfo | None:
    """Infer machine/station metadata from the recipe type and JSON properties."""
    norm_type = normalize_identifier(recipe_type)
    energy = data.get("energy", data.get("power", data.get("total_energy")))
    ticks = data.get("ticks", data.get("time", data.get("processingTime", data.get("duration"))))
    tier = data.get("tier")

    if isinstance(energy, float):
        energy = int(energy)
    if isinstance(ticks, float):
        ticks = int(ticks)
    if tier is not None:
        tier = str(tier)

    station_map: dict[str, tuple[str, str]] = {
        # Vanilla & Common Tables
        "minecraft:crafting_shaped": ("minecraft:crafting_table", "Crafting Table"),
        "minecraft:crafting_shapeless": ("minecraft:crafting_table", "Crafting Table"),
        "cucumber:shaped_no_mirror": ("minecraft:crafting_table", "Crafting Table"),
        "cucumber:shaped_tag": ("minecraft:crafting_table", "Crafting Table"),
        "cucumber:shaped_transfer_damage": ("minecraft:crafting_table", "Crafting Table"),
        "mekanism:mek_data": ("minecraft:crafting_table", "Crafting Table (MekData)"),
        "minecraft:smelting": ("minecraft:furnace", "Furnace"),
        "minecraft:blasting": ("minecraft:blast_furnace", "Blast Furnace"),
        "minecraft:smoking": ("minecraft:smoker", "Smoker"),
        "minecraft:campfire_cooking": ("minecraft:campfire", "Campfire"),
        "minecraft:stonecutting": ("minecraft:stonecutter", "Stonecutter"),
        "minecraft:smithing_transform": ("minecraft:smithing_table", "Smithing Table"),

        # Extended Crafting & Avaritia
        "extendedcrafting:shaped_table": ("extendedcrafting:crafting_table", "Extended Crafting Table"),
        "extendedcrafting:shapeless_table": ("extendedcrafting:crafting_table", "Extended Crafting Table"),
        "extendedcrafting:combination": ("extendedcrafting:crafting_core", "Crafting Core"),
        "extendedcrafting:compressor": ("extendedcrafting:compressor", "Quantum Compressor"),
        "extendedcrafting:shaped_ender_crafter": ("extendedcrafting:ender_crafter", "Ender Crafter"),
        "extendedcrafting:shaped_flux_crafter": ("extendedcrafting:flux_crafter", "Flux Crafter"),
        "avaritia:shaped_table": ("avaritia:extreme_crafting_table", "Extreme Crafting Table"),
        "avaritia:extreme_craft": ("avaritia:extreme_crafting_table", "Extreme Crafting Table"),
        "avaritia:compressor": ("avaritia:compressor", "Neutronium Compressor"),

        # Powah
        "powah:energizing": ("powah:energizing_orb", "Energizing Orb"),

        # Draconic Evolution
        "draconicevolution:fusion_crafting": ("draconicevolution:crafting_core", "Fusion Crafting Core"),

        # Mystical Agriculture
        "mysticalagriculture:infusion": ("mysticalagriculture:infusion_altar", "Infusion Altar"),
        "mysticalagriculture:awakening": ("mysticalagriculture:awakening_altar", "Awakening Altar"),
        "mysticalagriculture:reprocessor": ("mysticalagriculture:seed_reprocessor", "Seed Reprocessor"),
        "mysticalagriculture:enchanter": ("mysticalagriculture:enchanter", "Enchanter"),
        "mysticalagriculture:soul_extraction": ("mysticalagriculture:soul_extractor", "Soul Extractor"),
        "mysticalagriculture:soulium_spawner": ("mysticalagriculture:soulium_spawner", "Soulium Spawner"),

        # Industrial Foregoing
        "industrialforegoing:dissolution_chamber": ("industrialforegoing:dissolution_chamber", "Dissolution Chamber"),
        "industrialforegoing:fluid_extractor": ("industrialforegoing:fluid_extractor", "Fluid Extractor"),
        "industrialforegoing:laser_drill_ore": ("industrialforegoing:laser_drill", "Laser Drill (Ore)"),
        "industrialforegoing:laser_drill_fluid": ("industrialforegoing:laser_drill", "Laser Drill (Fluid)"),

        # Applied Energistics 2 & Addons
        "advanced_ae:reaction": ("advanced_ae:reaction_chamber", "Reaction Chamber"),
        "ae2:inscriber": ("ae2:inscriber", "Inscriber"),
        "ae2:charger": ("ae2:charger", "Charger"),
        "ae2:transform": ("minecraft:water_bucket", "In-World Transformation"),
        "neoecoae:integrated_working_station": ("neoecoae:integrated_working_station", "Integrated Working Station"),
        "neoecoae:storage_cell_disassembly": ("neoecoae:integrated_working_station", "Storage Cell Disassembly"),

        # Mekanism
        "evolvedmekanism:alloying": ("evolvedmekanism:alloyer", "Alloyer"),
        "mekanism:reaction": ("mekanism:pressurized_reaction_chamber", "Pressurized Reaction Chamber"),
        "mekanism:metallurgic_infusing": ("mekanism:metallurgic_infuser", "Metallurgic Infuser"),
        "mekanism:crushing": ("mekanism:crusher", "Crusher"),
        "mekanism:enriching": ("mekanism:enrichment_chamber", "Enrichment Chamber"),
        "mekanism:combining": ("mekanism:combiner", "Combiner"),
        "mekanism:compressing": ("mekanism:osmium_compressor", "Osmium Compressor"),
        "mekanism:purifying": ("mekanism:purification_chamber", "Purification Chamber"),
        "mekanism:injecting": ("mekanism:chemical_injection_chamber", "Chemical Injection Chamber"),
        "mekanism:sawing": ("mekanism:precision_sawmill", "Precision Sawmill"),
        "mekanism:nucleosynthesizing": ("mekanism:antiprotonic_nucleosynthesizer", "Antiprotonic Nucleosynthesizer"),
        "mekanism:oxidizing": ("mekanism:chemical_oxidizer", "Chemical Oxidizer"),
        "mekanism:dissolution": ("mekanism:chemical_dissolution_chamber", "Chemical Dissolution Chamber"),
        "mekanism:crystallizing": ("mekanism:chemical_crystallizer", "Chemical Crystallizer"),
        "mekanism:painting": ("mekanism:painting_machine", "Painting Machine"),
        "mekanism:pigment_extracting": ("mekanism:pigment_extractor", "Pigment Extractor"),
        "mekanism:pigment_mixing": ("mekanism:pigment_mixer", "Pigment Mixer"),
        "mekanism:infusion_conversion": ("mekanism:chemical_infuser", "Chemical Infuser"),
        "mekanism:rotary": ("mekanism:rotary_condensentrator", "Rotary Condensentrator"),
        "mekanism:nutritional_liquifying": ("mekanism:nutritional_liquifier", "Nutritional Liquifier"),

        # Thermal Series & Thermal Extra
        "thermal:crucible": ("thermal:machine_crucible", "Magma Crucible"),
        "thermal:pulverizer": ("thermal:machine_pulverizer", "Pulverizer"),
        "thermal:smelter": ("thermal:machine_smelter", "Induction Smelter"),
        "thermal:smelter_recycle": ("thermal:machine_smelter", "Induction Smelter"),
        "thermal:press": ("thermal:machine_press", "Multiservo Press"),
        "thermal:chiller": ("thermal:machine_chiller", "Blast Chiller"),
        "thermal:bottler": ("thermal:machine_bottler", "Fluid Encapsulator"),
        "thermal:crystallizer": ("thermal:machine_crystallizer", "Crystallizer"),
        "thermal:centrifuge": ("thermal:centrifuge", "Centrifuge"),
        "thermal:sawmill": ("thermal:machine_sawmill", "Sawmill"),
        "thermal:refinery": ("thermal:machine_refinery", "Fractionating Still"),
        "thermal:insolator": ("thermal:machine_insolator", "Phytogenic Insolator"),
        "thermal:brewer": ("thermal:machine_brewer", "Alchemical Imbuer"),
        "thermal:furnace": ("thermal:machine_furnace", "Redstone Furnace"),
        "thermal:crafter": ("thermal:machine_crafter", "Sequential Fabricator"),
        "thermal_extra:fluid_mixer": ("thermal_extra:machine_fluid_mixer", "Fluid Mixer"),
        "thermal_extra:endothermic_dehydrator": ("thermal_extra:machine_endothermic_dehydrator", "Endothermic Dehydrator"),

        # Ender IO
        "enderio:alloy_smelting": ("enderio:alloy_smelter", "Alloy Smelter"),
        "enderio:sag_milling": ("enderio:sag_mill", "SAG Mill"),
        "enderio:slicing": ("enderio:slice_and_splice", "Slice'N'Splice"),
        "enderio:soul_binding": ("enderio:soul_binder", "Soul Binder"),
        "enderio:enchanting": ("enderio:enchanter", "Enchanter"),

        # PneumaticCraft
        "pneumaticcraft:pressure_chamber": ("pneumaticcraft:pressure_chamber_wall", "Pressure Chamber"),
        "pneumaticcraft:thermo_plant": ("pneumaticcraft:thermopneumatic_processing_plant", "Thermopneumatic Processing Plant"),
        "pneumaticcraft:fluid_mixer": ("pneumaticcraft:fluid_mixer", "Fluid Mixer"),
        "pneumaticcraft:assembly_laser": ("pneumaticcraft:assembly_laser", "Assembly Laser"),

        # Botania & MythicBotany
        "botania:mana_infusion": ("botania:mana_pool", "Mana Pool"),
        "botania:runic_altar": ("botania:runic_altar", "Runic Altar"),
        "botania:petal_apothecary": ("botania:apothecary_default", "Petal Apothecary"),
        "botania:elven_trade": ("botania:alfheim_portal", "Alfheim Portal"),
        "botania:terra_plate": ("botania:terra_plate", "Terrestrial Agglomeration Plate"),
        "mythicbotany:rune_ritual": ("botania:runic_altar", "Rune Ritual"),

        # Blood Magic
        "bloodmagic:altar": ("bloodmagic:altar", "Blood Altar"),
        "bloodmagic:alchemytable": ("bloodmagic:alchemytable", "Alchemy Table"),
        "bloodmagic:soulforge": ("bloodmagic:soulforge", "Hellfire Forge"),
        "bloodmagic:arc": ("bloodmagic:arc", "Alchemical Reaction Chamber (ARC)"),
        "bloodmagic:array": ("bloodmagic:alchemyarray", "Alchemy Array"),

        # Ex Deorum
        "exdeorum:sieve": ("exdeorum:oak_sieve", "Sieve"),
        "exdeorum:compressed_sieve": ("exdeorum:oak_sieve", "Compressed Sieve"),
        "exdeorum:hammer": ("exdeorum:diamond_hammer", "Hammer"),
        "exdeorum:barrel_compost": ("minecraft:barrel", "Compost Barrel"),
        "exdeorum:barrel_mixing": ("minecraft:barrel", "Mixing Barrel"),
        "exdeorum:barrel_fluid_mixing": ("minecraft:barrel", "Fluid Mixing Barrel"),
        "exdeorum:water_crucible": ("exdeorum:porcelain_crucible", "Crucible"),
        "exdeorum:lava_crucible": ("exdeorum:porcelain_crucible", "Porcelain Crucible"),

        # Botany Pots
        "botanypots:crop": ("botanypots:terracotta_botany_pot", "Botany Pot"),
        "botanypots:soil": ("botanypots:terracotta_botany_pot", "Botany Pot"),

        # Actually Additions
        "actuallyadditions:crushing": ("actuallyadditions:crusher", "Crusher"),
        "actuallyadditions:empowering": ("actuallyadditions:empowerer", "Empowerer"),
        "actuallyadditions:color_change": ("actuallyadditions:atomic_reconstructor", "Atomic Reconstructor"),
        "actuallyadditions:laser": ("actuallyadditions:atomic_reconstructor", "Atomic Reconstructor"),
        "actuallyadditions:mining_lens": ("actuallyadditions:atomic_reconstructor", "Atomic Reconstructor (Mining Lens)"),

        # Cyclic
        "cyclic:solidifier": ("cyclic:solidifier", "Solidifier"),
        "cyclic:melter": ("cyclic:melter", "Melter"),
        "cyclic:crusher": ("cyclic:crusher", "Crusher"),

        # Integrated Dynamics
        "integrateddynamics:mechanical_squeezer": ("integrateddynamics:mechanical_squeezer", "Mechanical Squeezer"),
        "integrateddynamics:squeezer": ("integrateddynamics:mechanical_squeezer", "Squeezer"),
        "integrateddynamics:mechanical_drying_basin": ("integrateddynamics:mechanical_drying_basin", "Mechanical Drying Basin"),
        "integrateddynamics:drying_basin": ("integrateddynamics:mechanical_drying_basin", "Drying Basin"),

        # Hostile Neural Networks
        "hostilenetworks:sim_chamber": ("hostilenetworks:simulation_chamber", "Simulation Chamber"),
        "hostilenetworks:loot_fabricator": ("hostilenetworks:loot_fabricator", "Loot Fabricator"),

        # NuclearCraft
        "nuclearcraft:melter": ("nuclearcraft:melter", "Melter"),
        "nuclearcraft:target_chamber": ("nuclearcraft:target_chamber", "Target Chamber"),
        "nuclearcraft:ingot_former": ("nuclearcraft:ingot_former", "Ingot Former"),
        "nuclearcraft:fluid_infuser": ("nuclearcraft:fluid_infuser", "Fluid Infuser"),
        "nuclearcraft:chemical_reactor": ("nuclearcraft:chemical_reactor", "Chemical Reactor"),
        "nuclearcraft:manufactory": ("nuclearcraft:manufactory", "Manufactory"),
        "nuclearcraft:fission_reactor_controller": ("nuclearcraft:fission_reactor_controller", "Fission Reactor"),
        "nuclearcraft:subatomic_liquifier": ("nuclearcraft:subatomic_liquifier", "Subatomic Liquifier"),
        "nuclearcraft:alloy_smelter": ("nuclearcraft:alloy_smelter", "Alloy Smelter"),
        "nuclearcraft:fuel_reprocessor": ("nuclearcraft:fuel_reprocessor", "Fuel Reprocessor"),
        "nuclearcraft:pressurizer": ("nuclearcraft:pressurizer", "Pressurizer"),
        "nuclearcraft:centrifuge": ("nuclearcraft:centrifuge", "Centrifuge"),
        "nuclearcraft:kugelblitz_chamber": ("nuclearcraft:kugelblitz_controller", "Kugelblitz Chamber"),
        "nuclearcraft:assembler": ("nuclearcraft:assembler", "Assembler"),
        "nuclearcraft:collision_chamber": ("nuclearcraft:collision_chamber_controller", "Collision Chamber"),
        "nuclearcraft:decay_chamber": ("nuclearcraft:decay_chamber_controller", "Decay Chamber"),
        "nuclearcraft:decay_hastener": ("nuclearcraft:decay_hastener", "Decay Hastener"),
        "nuclearcraft:crystallizer": ("nuclearcraft:crystallizer", "Crystallizer"),
        "nuclearcraft:isotope_separator": ("nuclearcraft:isotope_separator", "Isotope Separator"),
        "nuclearcraft:msr_controller": ("nuclearcraft:msr_controller", "Molten Salt Reactor"),
        "nuclearcraft:fusion_core": ("nuclearcraft:fusion_core", "Fusion Core"),
        "nuclearcraft:supercooler": ("nuclearcraft:supercooler", "Supercooler"),
        "nuclearcraft:electrolyzer": ("nuclearcraft:electrolyzer", "Electrolyzer"),
        "nuclearcraft:extractor": ("nuclearcraft:extractor", "Extractor"),
        "nuclearcraft:pump": ("nuclearcraft:pump", "Pump"),
        "nuclearcraft:steam_turbine": ("nuclearcraft:steam_turbine", "Steam Turbine"),

        # Molecular Manipulator
        "molecularmanipulator:matter_fabrication": ("molecularmanipulator:matter_fabricator", "Matter Fabricator"),

        # Woot Revived
        "woot_revived:dye_liquifier": ("woot_revived:dye_liquifier", "Dye Liquifier"),
        "woot_revived:item_infuser": ("woot_revived:item_infuser", "Item Infuser"),
        "woot_revived:fluid_infuser": ("woot_revived:fluid_infuser", "Fluid Infuser"),
        "woot_revived:stygian_anvil": ("woot_revived:stygian_anvil", "Stygian Anvil"),

        # RFTools Utility
        "rftoolsutility:spawner": ("rftoolsutility:spawner", "Spawner"),
        "rftoolsutility:crafter": ("rftoolsutility:crafter1", "Crafter"),

        # Void Miners
        "voidminers:miner": ("voidminers:miner_controller", "Void Miner"),
    }

    if norm_type in station_map:
        st_id, st_name = station_map[norm_type]
        return MachineInfo(
            station_id=st_id,
            station_name=st_name,
            energy_fe=energy if isinstance(energy, int) else None,
            ticks=ticks if isinstance(ticks, int) else None,
            tier=tier,
        )

    # Generic fallback for any machine mod (e.g. nuclearcraft:*, thermal_extra:*, crazyae2addons:*)
    return MachineInfo(
        station_id=norm_type,
        station_name=norm_type.replace(":", " - ").replace("_", " ").title(),
        energy_fe=energy if isinstance(energy, int) else None,
        ticks=ticks if isinstance(ticks, int) else None,
        tier=tier,
    )


def parse_recipe_json(
    recipe_id: str,
    data: Any,
    data_source: DataSource,
    source_path: str,
    loaded_mods: set[str] | None = None,
    tag_registry: TagRegistry | None = None,
) -> tuple[NormalizedRecipe | None, bool]:
    """
    Parse a raw JSON recipe dictionary into a NormalizedRecipe.

    Returns `(recipe_or_none, skipped_by_condition)`.
    - If the JSON is `{}` (empty datapack override removal), returns a recipe with `ValidationStatus.REMOVED`.
    - If a Forge/Bookshelf condition evaluates to False, returns `(None, True)`.
    """
    norm_id = normalize_identifier(recipe_id)
    source_mod = norm_id.split(":", 1)[0] if ":" in norm_id else "minecraft"
    mods_set = loaded_mods or {"minecraft", "forge", "kubejs"}

    if not isinstance(data, dict):
        return (
            NormalizedRecipe(
                recipe_id=norm_id,
                recipe_type="unknown:invalid",
                source_mod=source_mod,
                data_source=data_source,
                source_path=source_path,
                validation_status=ValidationStatus.INVALID,
                raw_data=data,
                warnings=["Recipe payload is not a JSON object"],
            ),
            False,
        )

    # Empty JSON {} in a datapack is Minecraft's official way to disable/remove a recipe by ID
    if len(data) == 0:
        return (
            NormalizedRecipe(
                recipe_id=norm_id,
                recipe_type="minecraft:empty_override",
                source_mod=source_mod,
                data_source=data_source,
                source_path=source_path,
                validation_status=ValidationStatus.REMOVED,
                warnings=["Empty JSON object {} disables this recipe ID"],
            ),
            False,
        )

    # Top-level Forge conditions check
    if "conditions" in data and isinstance(data["conditions"], list):
        if not evaluate_conditions_list(data["conditions"], mods_set, tag_registry):
            return (None, True)

    raw_type = str(data.get("type", "")).strip()
    if not raw_type:
        return (
            NormalizedRecipe(
                recipe_id=norm_id,
                recipe_type="unknown:missing_type",
                source_mod=source_mod,
                data_source=data_source,
                source_path=source_path,
                validation_status=ValidationStatus.INVALID,
                raw_data=data,
                warnings=["Missing 'type' field in recipe JSON"],
            ),
            False,
        )

    norm_type = normalize_identifier(raw_type)

    # 1. Unwrap forge:conditional and bookshelf:item_exists
    if norm_type in ("forge:conditional", "bookshelf:item_exists"):
        recipes_list = data.get("recipes", [])
        if isinstance(recipes_list, list):
            for entry in recipes_list:
                if not isinstance(entry, dict):
                    continue
                conds = entry.get("conditions", [])
                if evaluate_conditions_list(conds, mods_set, tag_registry):
                    inner_recipe = entry.get("recipe")
                    if isinstance(inner_recipe, dict):
                        return parse_recipe_json(
                            norm_id,
                            inner_recipe,
                            data_source=data_source,
                            source_path=source_path,
                            loaded_mods=mods_set,
                            tag_registry=tag_registry,
                        )
            return (None, True)

    # 2. Check special code-only recipes (e.g. armor dye, banner duplicate)
    if norm_type in SPECIAL_DYNAMIC_RECIPE_TYPES or ":crafting_special_" in norm_type:
        return (
            NormalizedRecipe(
                recipe_id=norm_id,
                recipe_type=norm_type,
                source_mod=source_mod,
                data_source=data_source,
                source_path=source_path,
                validation_status=ValidationStatus.UNSUPPORTED,
                raw_data=data,
                warnings=[f"Dynamic code-driven recipe type '{norm_type}' has no fixed static items"],
            ),
            False,
        )

    inputs: list[IngredientSlot] = []
    outputs: list[RecipeStack] = []
    extra_data: dict[str, Any] = {}
    warnings: list[str] = []

    # 3. Shaped grid recipes (Vanilla, Extended Crafting, Avaritia, Mekanism MekData, Cucumber)
    if "pattern" in data and "key" in data and isinstance(data["pattern"], list) and isinstance(data["key"], dict):
        pattern = [str(r) for r in data["pattern"]]
        inputs.extend(_extract_shaped_inputs(pattern, data["key"]))
        extra_data["pattern"] = pattern
        if "tier" in data:
            extra_data["tier"] = data["tier"]
        for out_key in ("result", "output"):
            if out_key in data:
                outputs.extend(parse_stack_Entry(data[out_key]))
                break

    # 4. AE2 Inscriber (ingredients.top, ingredients.middle, ingredients.bottom)
    elif norm_type == "ae2:inscriber" and isinstance(data.get("ingredients"), dict):
        ing_map = data["ingredients"]
        mode = str(data.get("mode", "inscribe"))
        extra_data["mode"] = mode
        for pos in ("middle", "top", "bottom"):
            if pos in ing_map:
                # In 'inscribe' mode, top and bottom presses are NOT consumed!
                is_consumed = True if (pos == "middle" or mode == "press") else False
                slot = build_slot(ing_map[pos], slot_key=pos, consumable=is_consumed)
                if slot:
                    inputs.append(slot)
        if "result" in data:
            outputs.extend(parse_stack_Entry(data["result"]))

    # 5. Draconic Evolution Fusion Crafting
    elif norm_type == "draconicevolution:fusion_crafting":
        if "catalyst" in data:
            cat_slot = build_slot(data["catalyst"], slot_key="catalyst", consumable=True)
            if cat_slot:
                inputs.append(cat_slot)
        for idx, ing in enumerate(data.get("ingredients", [])):
            slot = build_slot(ing, slot_key=f"injector_{idx}")
            if slot:
                inputs.append(slot)
        if "result" in data:
            outputs.extend(parse_stack_Entry(data["result"]))
        if "total_energy" in data:
            extra_data["total_energy"] = data["total_energy"]

    # 6. ExDeorum Sieve & Hammer
    elif norm_type in ("exdeorum:sieve", "exdeorum:compressed_sieve", "exdeorum:hammer", "exdeorum:crook"):
        if "ingredient" in data:
            slot = build_slot(data["ingredient"], slot_key="input")
            if slot:
                inputs.append(slot)
        if "mesh" in data:
            mesh_slot = build_slot(data["mesh"], slot_key="mesh", consumable=False)
            if mesh_slot:
                inputs.append(mesh_slot)
        res_id = data.get("result")
        res_amt = data.get("result_amount", 1)
        chance = 1.0
        if isinstance(res_amt, dict):
            # Binomial distribution {"type": "minecraft:binomial", "n": 1, "p": 0.25}
            n_val = float(res_amt.get("n", 1))
            p_val = float(res_amt.get("p", 1.0))
            chance = round(p_val, 4)
            res_amt = max(1, int(round(n_val)))
            extra_data["binomial"] = {"n": n_val, "p": p_val}
        if isinstance(res_id, str):
            outputs.append(
                RecipeStack(
                    resource_id=res_id,
                    count=res_amt if isinstance(res_amt, (int, float)) else 1,
                    nbt=data.get("result_nbt"),
                    chance=chance,
                )
            )
        elif isinstance(res_id, dict):
            outputs.extend(parse_stack_Entry(res_id))

    # 7. BotanyPots Crop (seed -> multiple drops)
    elif norm_type == "botanypots:crop":
        if "seed" in data:
            seed_slot = build_slot(data["seed"], slot_key="seed", consumable=False)
            if seed_slot:
                inputs.append(seed_slot)
        for drop in data.get("drops", []):
            if isinstance(drop, dict) and "output" in drop:
                st_list = parse_stack_Entry(drop["output"])
                drop_chance = float(drop.get("chance", 1.0))
                for st in st_list:
                    st.chance = drop_chance
                    outputs.append(st)
        if outputs:
            for idx, out in enumerate(outputs):
                out.is_primary = idx == 0

    # 8. Functional Storage Custom Compacting (higher_input <-> lower_input)
    elif norm_type == "functionalstorage:custom_compacting":
        lower = parse_stack_Entry(data.get("lower_input"))
        higher = parse_stack_Entry(data.get("higher_input"))
        if lower and higher:
            inputs.append(
                IngredientSlot(alternatives=[RecipeStack(lower[0].resource_id, 1)], count=lower[0].count)
            )
            outputs.append(higher[0])

    # 9. General Heuristic Extraction for Machine, Magic, Smelting, Smithing, and Shapeless Recipes
    else:
        # 9a. Single or list item inputs
        for in_key in (
            "ingredient",
            "ingredients",
            "input",
            "inputs",
            "item_in",
            "item_input",
            "itemInput",
            "itemInputs",
            "mainInput",
            "extraInput",
            "secondaryInput",
            "input_items",
            "reactants",
            "catalysts",
            "pedestals",
            "additives",
            "consumables",
            "input0",
            "input1",
            "input2",
            "input3",
            "item",
            "material",
            "from",
            "cell",
            "terminalA",
            "terminalB",
        ):
            if in_key not in data:
                continue
            val = data[in_key]
            # Distinguish array of separate slots vs single ingredient with alternative array
            if in_key in (
                "ingredients",
                "inputs",
                "itemInputs",
                "input_items",
                "reactants",
                "pedestals",
                "additives",
                "consumables",
            ) and isinstance(val, list):
                for idx, elem in enumerate(val):
                    slot = build_slot(elem, slot_key=f"{in_key}_{idx}")
                    if slot:
                        inputs.append(slot)
            else:
                slot = build_slot(val, slot_key=in_key)
                if slot:
                    inputs.append(slot)

        # 9b. Smithing table & casting fields (template, base, addition, cast)
        for smith_key in ("template", "base", "addition", "cast"):
            if smith_key in data:
                is_consumed = bool(data.get("cast_consumed", True)) if smith_key == "cast" else None
                slot = build_slot(data[smith_key], slot_key=smith_key, consumable=is_consumed)
                if slot:
                    inputs.append(slot)

        # 9c. Fluid inputs
        for fl_in_key in (
            "fluidInput",
            "fluidInputs",
            "inputFluid",
            "inputFluids",
            "fluid_in",
            "fluid_input",
            "fluid",
        ):
            if fl_in_key in data:
                val = data[fl_in_key]
                if fl_in_key in ("fluidInputs", "inputFluids") and isinstance(val, list):
                    for idx, elem in enumerate(val):
                        slot = build_slot(elem, slot_key=f"fluid_{idx}", default_type=ResourceType.FLUID)
                        if slot:
                            inputs.append(slot)
                else:
                    slot = build_slot(val, slot_key=fl_in_key, default_type=ResourceType.FLUID)
                    if slot:
                        inputs.append(slot)

        # 9d. Gas / Chemical / Infuse inputs (Mekanism, etc.)
        for gas_in_key in ("gasInput", "chemicalInput", "infusionInput", "slurryInput", "pigmentInput"):
            if gas_in_key in data:
                slot = build_slot(data[gas_in_key], slot_key=gas_in_key, default_type=ResourceType.GAS)
                if slot:
                    inputs.append(slot)

        # 9e. Aggregate matching ingredient slots if shapeless
        if norm_type in ("minecraft:crafting_shapeless", "extendedcrafting:shapeless_table"):
            merged: list[IngredientSlot] = []
            for s in inputs:
                if len(s.alternatives) == 1 and s.consumable:
                    match = next(
                        (
                            m
                            for m in merged
                            if len(m.alternatives) == 1
                            and m.alternatives[0].item_key == s.alternatives[0].item_key
                            and m.consumable
                        ),
                        None,
                    )
                    if match:
                        match.count += s.count
                        continue
                merged.append(s)
            inputs = merged

        # 9f. Outputs extraction (Items, Fluids, Gases)
        for out_key in (
            "result",
            "results",
            "output",
            "outputs",
            "mainOutput",
            "secondaryOutput",
            "itemOutput",
            "item_output",
            "itemOutputs",
            "output_items",
            "cell_disassembly_items",
            "to",
        ):
            if out_key not in data:
                continue
            val = data[out_key]
            if out_key in (
                "results",
                "outputs",
                "itemOutputs",
                "output_items",
                "cell_disassembly_items",
            ) and isinstance(val, list):
                for elem in val:
                    for st in parse_stack_Entry(elem):
                        if outputs:
                            st.is_primary = False
                        outputs.append(st)
            else:
                for st in parse_stack_Entry(val):
                    if out_key == "secondaryOutput" or outputs:
                        st.is_primary = False
                        if "secondaryChance" in data:
                            st.chance = float(data["secondaryChance"])
                    outputs.append(st)

        # Integrated Dynamics Squeezer nested result {"result": {"items": [...], "fluid": {...}}}
        if isinstance(data.get("result"), dict):
            res_dict = data["result"]
            if "fluid" in res_dict:
                for st in parse_stack_Entry(res_dict["fluid"], default_type=ResourceType.FLUID):
                    if outputs:
                        st.is_primary = False
                    outputs.append(st)

        for fl_out_key in (
            "fluidOutput",
            "fluidOutputs",
            "outputFluid",
            "outputFluids",
            "fluid_output",
            "fluidResult",
        ):
            if fl_out_key in data:
                val = data[fl_out_key]
                if isinstance(val, list):
                    for elem in val:
                        for st in parse_stack_Entry(elem, default_type=ResourceType.FLUID):
                            if outputs:
                                st.is_primary = False
                            outputs.append(st)
                else:
                    for st in parse_stack_Entry(val, default_type=ResourceType.FLUID):
                        if outputs:
                            st.is_primary = False
                        outputs.append(st)

        for gas_out_key in ("gasOutput", "chemicalOutput", "outputGas", "infusionOutput", "slurryOutput"):
            if gas_out_key in data:
                for st in parse_stack_Entry(data[gas_out_key], default_type=ResourceType.GAS):
                    if outputs:
                        st.is_primary = False
                    outputs.append(st)

        # Single top-level "count" modifier for smelting/stonecutting where "result" is a string
        if len(outputs) == 1 and isinstance(data.get("result"), str) and "count" in data:
            outputs[0].count = int(data["count"])

    machine_info = _infer_machine_info(norm_type, data)

    if inputs and outputs:
        status = ValidationStatus.VALID
        raw_preserved = None
    elif outputs or inputs:
        status = ValidationStatus.PARTIAL
        raw_preserved = data
        warnings.append(
            f"Recipe '{norm_id}' ({norm_type}) parsed partially (inputs={len(inputs)}, outputs={len(outputs)})"
        )
    else:
        status = ValidationStatus.UNSUPPORTED
        raw_preserved = data
        warnings.append(f"Recipe type '{norm_type}' structure did not yield standard inputs/outputs")

    return (
        NormalizedRecipe(
            recipe_id=norm_id,
            recipe_type=norm_type,
            source_mod=source_mod,
            data_source=data_source,
            source_path=source_path,
            outputs=outputs,
            inputs=inputs,
            machine_info=machine_info,
            validation_status=status,
            extra_data=extra_data,
            raw_data=raw_preserved,
            warnings=warnings,
        ),
        False,
    )

