"""Parser and processor for KubeJS scripts, Masterful Machinery processes, and Singularity configs."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from backend.importer.adapters import build_slot, parse_recipe_json, parse_stack_Entry
from backend.importer.tags import TagRegistry
from backend.models.recipe import (
    DataSource,
    IngredientSlot,
    MachineInfo,
    NormalizedRecipe,
    RecipeStack,
    ResourceType,
    ValidationStatus,
    normalize_identifier,
)


@dataclass
class RemovalFilter:
    """Represents a recipe removal rule from KubeJS event.remove(...)."""

    recipe_id: str | None = None
    output: str | None = None
    output_regex: re.Pattern[str] | None = None
    input_item: str | None = None
    recipe_type: str | None = None
    mod: str | None = None

    def matches(self, recipe: NormalizedRecipe) -> bool:
        if recipe.validation_status == ValidationStatus.REMOVED:
            return False
        if self.recipe_id and recipe.recipe_id != normalize_identifier(self.recipe_id):
            return False
        if self.mod and recipe.source_mod != self.mod:
            return False
        if self.recipe_type and recipe.recipe_type != normalize_identifier(self.recipe_type):
            return False
        if self.output:
            norm_out = normalize_identifier(self.output.lstrip("#"))
            if not any(o.resource_id == norm_out for o in recipe.outputs):
                return False
        if self.output_regex:
            if not any(self.output_regex.search(o.resource_id) for o in recipe.outputs):
                return False
        if self.input_item:
            if not any(slot.matches_id(self.input_item) for slot in recipe.inputs):
                return False
        # At least one criterion must be active
        return any(
            x is not None
            for x in (
                self.recipe_id,
                self.output,
                self.output_regex,
                self.input_item,
                self.recipe_type,
                self.mod,
            )
        )


@dataclass
class ReplacementRule:
    """Represents an event.replaceInput or event.replaceOutput call."""

    is_output: bool
    filter_criteria: RemovalFilter
    target_item: str
    replacement_item: str


def strip_js_comments(js_text: str) -> str:
    """Remove // single-line and /* multi-line */ comments while preserving string literals."""
    pattern = re.compile(
        r'("(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|`(?:\\.|[^`\\])*`)|(/\*[\s\S]*?\*/|//[^\r\n]*)'
    )
    return pattern.sub(lambda m: m.group(1) if m.group(1) else "", js_text)


def extract_balanced_block(text: str, start_idx: int, open_ch: str = "{", close_ch: str = "}") -> tuple[str, int]:
    """Extract a balanced {...}, [...], or (...) substring starting at or after start_idx."""
    pos = text.find(open_ch, start_idx)
    if pos == -1:
        return ("", -1)
    depth = 0
    in_str: str | None = None
    escaped = False
    for idx in range(pos, len(text)):
        ch = text[idx]
        if escaped:
            escaped = False
            continue
        if ch == "\\":
            escaped = True
            continue
        if in_str:
            if ch == in_str:
                in_str = None
            continue
        if ch in ('"', "'", "`"):
            in_str = ch
            continue
        if ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                return (text[pos : idx + 1], idx + 1)
    return ("", -1)


def split_top_level_args(arg_str: str) -> list[str]:
    """Split a comma-separated JS argument list at the top level (ignoring commas inside {}, [], ())."""
    args: list[str] = []
    current: list[str] = []
    depth_brace = 0
    depth_bracket = 0
    depth_paren = 0
    in_str: str | None = None
    escaped = False

    for ch in arg_str:
        if escaped:
            current.append(ch)
            escaped = False
            continue
        if ch == "\\":
            current.append(ch)
            escaped = True
            continue
        if in_str:
            current.append(ch)
            if ch == in_str:
                in_str = None
            continue
        if ch in ('"', "'", "`"):
            in_str = ch
            current.append(ch)
            continue
        if ch == "{":
            depth_brace += 1
        elif ch == "}":
            depth_brace -= 1
        elif ch == "[":
            depth_bracket += 1
        elif ch == "]":
            depth_bracket -= 1
        elif ch == "(":
            depth_paren += 1
        elif ch == ")":
            depth_paren -= 1
        elif ch == "," and depth_brace == 0 and depth_bracket == 0 and depth_paren == 0:
            args.append("".join(current).strip())
            current = []
            continue
        current.append(ch)

    tail = "".join(current).strip()
    if tail:
        args.append(tail)
    return args


def js_object_to_python(js_expr: str) -> Any:
    """Convert a JavaScript object/array literal into a Python dict/list."""
    cleaned = strip_js_comments(js_expr).strip()
    if not cleaned:
        return None

    # Replace Item.of('id', '{nbt}').weakNBT() or Item.of('id', count) with JSON equivalent
    cleaned = re.sub(
        r"Item\.of\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]+)['\"]\s*\)(?:\.weakNBT\(\)|\.strongNBT\(\))?",
        lambda m: json.dumps({"item": m.group(1), "nbt": m.group(2)}),
        cleaned,
    )
    cleaned = re.sub(
        r"Item\.of\(\s*['\"]([^'\"]+)['\"]\s*,\s*(\d+)\s*\)",
        lambda m: json.dumps({"item": m.group(1), "count": int(m.group(2))}),
        cleaned,
    )
    cleaned = re.sub(
        r"Item\.of\(\s*['\"]([^'\"]+)['\"]\s*\)(?:\.weakNBT\(\)|\.strongNBT\(\))?",
        lambda m: json.dumps({"item": m.group(1)}),
        cleaned,
    )
    cleaned = re.sub(r"\.weakNBT\(\)|\.strongNBT\(\)", "", cleaned)

    # Convert single-quoted strings to double-quoted JSON strings carefully
    def _quote_replacer(match: re.Match[str]) -> str:
        s = match.group(0)
        if s.startswith("'") and s.endswith("'"):
            inner = s[1:-1].replace("\\'", "'").replace('"', '\\"')
            return f'"{inner}"'
        return s

    cleaned = re.sub(r"'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"", _quote_replacer, cleaned)

    # Quote unquoted object keys: { type: "foo", count: 1 } -> { "type": "foo", "count": 1 }
    cleaned = re.sub(r"(?<=[{,])\s*([a-zA-Z0-9_]+)\s*:", r' "\1":', cleaned)

    # Remove trailing commas before } or ]
    cleaned = re.sub(r",\s*([}\]])", r"\1", cleaned)

    try:
        return json.loads(cleaned)
    except Exception:
        return None


def parse_js_item_expr(expr: str) -> RecipeStack | None:
    """Parse a JS item expression like `'9x kubejs:infinity_6'` or `Item.of('id', '{...}')`."""
    cleaned = expr.strip()
    cleaned = re.sub(r"\.weakNBT\(\)|\.strongNBT\(\)", "", cleaned).strip()

    m_item_nbt = re.match(
        r"^Item\.of\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]([\s\S]+)['\"]\s*\)$",
        cleaned,
    )
    if m_item_nbt:
        return RecipeStack(resource_id=m_item_nbt.group(1), count=1, nbt=m_item_nbt.group(2))

    m_item_cnt = re.match(
        r"^Item\.of\(\s*['\"]([^'\"]+)['\"]\s*,\s*(\d+)\s*\)$",
        cleaned,
    )
    if m_item_cnt:
        return RecipeStack(resource_id=m_item_cnt.group(1), count=int(m_item_cnt.group(2)))

    m_item_simple = re.match(r"^Item\.of\(\s*['\"]([^'\"]+)['\"]\s*\)$", cleaned)
    if m_item_simple:
        return RecipeStack(resource_id=m_item_simple.group(1), count=1)

    if (cleaned.startswith("'") and cleaned.endswith("'")) or (
        cleaned.startswith('"') and cleaned.endswith('"')
    ):
        raw_str = cleaned[1:-1].strip()
        stacks = parse_stack_Entry(raw_str)
        return stacks[0] if stacks else None

    parsed_obj = js_object_to_python(cleaned)
    if parsed_obj is not None:
        stacks = parse_stack_Entry(parsed_obj)
        return stacks[0] if stacks else None

    return None


def _make_kubejs_recipe_id(prefix: str, output_id: str, source_path: str, index: int) -> str:
    """Generate a deterministic KubeJS recipe ID when .id(...) is not explicitly provided."""
    short_hash = hashlib.md5(f"{source_path}:{index}:{output_id}".encode("utf-8")).hexdigest()[:8]
    clean_out = output_id.replace(":", "_")
    return f"kubejs:{prefix}_{clean_out}_{short_hash}"


def _expand_helper_call(
    helper_name: str,
    output_stack: RecipeStack,
    input_stacks: list[RecipeStack],
    recipe_id: str,
    source_path: str,
) -> NormalizedRecipe | None:
    """Convert a call to one of the helper functions in `kubejs/server_scripts/functions.js` into a NormalizedRecipe."""
    pattern: list[str] = []
    key_map: dict[str, RecipeStack] = {}

    if helper_name == "shapeless":
        slots: list[IngredientSlot] = []
        for st in input_stacks:
            slot = IngredientSlot(
                alternatives=[RecipeStack(st.resource_id, 1, st.resource_type, st.nbt)],
                count=st.count,
                consumable=not (st.resource_id in ("kubejs:fake_philosophers_stone", "projecte:philosophers_stone")),
            )
            slots.append(slot)
        return NormalizedRecipe(
            recipe_id=recipe_id,
            recipe_type="minecraft:crafting_shapeless",
            source_mod="kubejs",
            data_source=DataSource.KUBEJS_SCRIPT,
            source_path=source_path,
            outputs=[output_stack],
            inputs=slots,
            machine_info=MachineInfo("minecraft:crafting_table", "Crafting Table"),
        )

    if helper_name in (
        "shapelessdraconic",
        "reverseshapelessdraconic",
        "shapelessdraconicadditions",
        "reverseshapelessdraconicadditions",
    ):
        raw_name = output_stack.resource_id.split(":", 1)[-1]
        if helper_name == "shapelessdraconic":
            out_id, in_id = f"draconicevolution:{raw_name}", f"kubejs:{raw_name}"
        elif helper_name == "reverseshapelessdraconic":
            out_id, in_id = f"kubejs:{raw_name}", f"draconicevolution:{raw_name}"
        elif helper_name == "shapelessdraconicadditions":
            out_id, in_id = f"draconicadditions:{raw_name}", f"kubejs:{raw_name}"
        else:
            out_id, in_id = f"kubejs:{raw_name}", f"draconicadditions:{raw_name}"
        return NormalizedRecipe(
            recipe_id=recipe_id,
            recipe_type="minecraft:crafting_shapeless",
            source_mod="kubejs",
            data_source=DataSource.KUBEJS_SCRIPT,
            source_path=source_path,
            outputs=[RecipeStack(out_id, 1)],
            inputs=[IngredientSlot(alternatives=[RecipeStack(in_id, 1)], count=1)],
            machine_info=MachineInfo("minecraft:crafting_table", "Crafting Table"),
        )

    if helper_name == "create323" and len(input_stacks) >= 1:
        pattern = ["000", "0 0", "000"]
        key_map = {"0": input_stacks[0]}
    elif helper_name == "create_conduit_craft" and len(input_stacks) >= 2:
        pattern = ["000", "111", "000"]
        key_map = {"0": input_stacks[0], "1": input_stacks[1]}
    elif helper_name == "create_conduit_craft2" and len(input_stacks) >= 3:
        pattern = ["000", "121", "000"]
        key_map = {"0": input_stacks[0], "1": input_stacks[1], "2": input_stacks[2]}
    elif helper_name == "create2x2" and len(input_stacks) >= 4:
        pattern = ["01", "23"]
        key_map = {str(i): input_stacks[i] for i in range(4)}
    elif helper_name == "create2x2same" and len(input_stacks) >= 1:
        pattern = ["00", "00"]
        key_map = {"0": input_stacks[0]}
    elif helper_name == "create3x3" and len(input_stacks) >= 9:
        pattern = ["012", "345", "678"]
        key_map = {str(i): input_stacks[i] for i in range(9)}
    elif helper_name == "create3x3_EV_EX" and len(input_stacks) >= 1:
        pattern = ["010", "232", "010"]
        key_map = {
            "0": RecipeStack("evolvedmekanism:alloy_creative", 1),
            "1": RecipeStack("evolvedmekanism:creative_control_circuit", 1),
            "2": RecipeStack("minecraft:nether_star", 1),
            "3": input_stacks[0],
        }
    elif helper_name == "create3x3same" and len(input_stacks) >= 1:
        pattern = ["000", "000", "000"]
        key_map = {"0": input_stacks[0]}
    elif helper_name == "seedtiercrafting1" and len(input_stacks) >= 1:
        pattern = ["121", "202", "121"]
        key_map = {
            "0": RecipeStack("kubejs:tier1_crafting_seed", 1),
            "1": input_stacks[0],
            "2": RecipeStack("mysticalagriculture:inferium_essence", 1),
        }
    elif helper_name == "seedtiercrafting2" and len(input_stacks) >= 1:
        pattern = ["121", "202", "121"]
        key_map = {
            "0": RecipeStack("kubejs:tier2_crafting_seed", 1),
            "1": input_stacks[0],
            "2": RecipeStack("mysticalagriculture:prudentium_essence", 1),
        }
    elif helper_name == "seedtiercrafting2extra" and len(input_stacks) >= 2:
        pattern = ["123", "202", "321"]
        key_map = {
            "0": RecipeStack("kubejs:tier2_crafting_seed", 1),
            "1": input_stacks[0],
            "2": RecipeStack("mysticalagriculture:prudentium_essence", 1),
            "3": input_stacks[1],
        }
    elif helper_name == "seedtiermobcrafting2" and len(input_stacks) >= 1:
        pattern = ["121", "202", "121"]
        key_map = {
            "0": RecipeStack("mysticalagriculture:soulium_seed_base", 1),
            "1": input_stacks[0],
            "2": RecipeStack("mysticalagriculture:prudentium_essence", 1),
        }
    elif helper_name == "create3x3jetpack" and len(input_stacks) >= 4:
        pattern = ["010", "020", "343"]
        key_map = {
            "0": input_stacks[0],
            "1": input_stacks[1],
            "2": input_stacks[2],
            "3": input_stacks[3],
        }
    else:
        return None

    freq: dict[str, int] = {}
    for row in pattern:
        for ch in row:
            if ch != " " and ch in key_map:
                freq[ch] = freq.get(ch, 0) + 1

    slots = []
    for sym, count in freq.items():
        st = key_map[sym]
        if st.resource_id == "minecraft:air":
            continue
        slots.append(
            IngredientSlot(
                alternatives=[RecipeStack(st.resource_id, 1, st.resource_type, st.nbt)],
                count=st.count * count,
                slot_key=sym,
            )
        )

    return NormalizedRecipe(
        recipe_id=recipe_id,
        recipe_type="minecraft:crafting_shaped",
        source_mod="kubejs",
        data_source=DataSource.KUBEJS_SCRIPT,
        source_path=source_path,
        outputs=[output_stack],
        inputs=slots,
        machine_info=MachineInfo("minecraft:crafting_table", "Crafting Table"),
        extra_data={"pattern": pattern, "helper": helper_name},
    )


def parse_masterful_machinery_processes(
    js_text: str,
    source_path: str,
) -> list[NormalizedRecipe]:
    """Extract all `MMEvents.createProcesses` chains from a KubeJS script."""
    if "MMEvents.createProcesses" not in js_text:
        return []

    clean = strip_js_comments(js_text)
    recipes: list[NormalizedRecipe] = []

    # Split by .create('mm:...' or "mm:...")
    create_matches = list(re.finditer(r"\.create\s*\(\s*['\"]([^'\"]+)['\"]\s*\)", clean))
    for i, m in enumerate(create_matches):
        recipe_id = normalize_identifier(m.group(1), default_namespace="mm")
        start_pos = m.end()
        end_pos = create_matches[i + 1].start() if i + 1 < len(create_matches) else len(clean)
        chain_segment = clean[start_pos:end_pos]

        struct_match = re.search(r"\.structureId\s*\(\s*['\"]([^'\"]+)['\"]\s*\)", chain_segment)
        structure_id = normalize_identifier(struct_match.group(1), default_namespace="mm") if struct_match else "mm:multiblock"

        ticks_match = re.search(r"\.ticks\s*\(\s*(\d+)\s*\)", chain_segment)
        ticks = int(ticks_match.group(1)) if ticks_match else 1

        inputs: list[IngredientSlot] = []
        outputs: list[RecipeStack] = []
        energy_fe: int | None = None

        # Find all .input({...}) and .output({...}) calls
        for io_match in re.finditer(r"\.(input|output)\s*\(", chain_segment):
            kind = io_match.group(1)
            obj_str, _ = extract_balanced_block(chain_segment, io_match.end() - 1, "(", ")")
            if not obj_str:
                continue
            inner_brace, _ = extract_balanced_block(obj_str, 0, "{", "}")
            if not inner_brace:
                continue
            parsed = js_object_to_python(inner_brace)
            if not isinstance(parsed, dict):
                continue

            chance = float(parsed.get("chance", 1.0))
            ing_data = parsed.get("ingredient", parsed)
            if not isinstance(ing_data, dict):
                continue

            ing_type = str(ing_data.get("type", ""))
            if ing_type == "mm:energy":
                amt = int(ing_data.get("amount", 0))
                if kind == "input":
                    energy_fe = (energy_fe or 0) + amt
                else:
                    outputs.append(
                        RecipeStack("forge:fe", amt, ResourceType.ENERGY, chance=chance, is_primary=False)
                    )
                continue

            default_r_type = ResourceType.ITEM
            if ing_type == "mm:fluid" or "fluid" in ing_data:
                default_r_type = ResourceType.FLUID
            elif ing_type.startswith("mm:mekanism/") or "gas" in ing_data or "chemical" in ing_data:
                default_r_type = ResourceType.GAS

            if kind == "input":
                slot = build_slot(
                    ing_data,
                    default_type=default_r_type,
                    consumable=(chance > 0.0),
                )
                if slot:
                    slot.chance = chance
                    if chance == 0.0:
                        slot.consumable = False
                    inputs.append(slot)
            else:
                out_stacks = parse_stack_Entry(ing_data, default_type=default_r_type)
                for st in out_stacks:
                    st.chance = chance
                    if outputs:
                        st.is_primary = False
                    outputs.append(st)

        station_label = structure_id.split(":", 1)[-1].replace("_structure", "").replace("_", " ").title()
        machine_info = MachineInfo(
            station_id=structure_id,
            station_name=f"MM Multiblock: {station_label}",
            structure_id=structure_id,
            energy_fe=energy_fe,
            ticks=ticks,
        )

        status = ValidationStatus.VALID if (inputs and outputs) else ValidationStatus.PARTIAL
        recipes.append(
            NormalizedRecipe(
                recipe_id=recipe_id,
                recipe_type="mm:process",
                source_mod="mm",
                data_source=DataSource.KUBEJS_SCRIPT,
                source_path=source_path,
                outputs=outputs,
                inputs=inputs,
                machine_info=machine_info,
                validation_status=status,
            )
        )

    return recipes


def parse_singularities_from_config(config_dir: Path) -> list[NormalizedRecipe]:
    """Generate Quantum Compressor and Ultimate Singularity recipes from config/extendedcrafting/singularities/*.json."""
    sing_dir = config_dir / "extendedcrafting" / "singularities"
    if not sing_dir.exists():
        return []

    recipes: list[NormalizedRecipe] = []
    ultimate_inputs: list[IngredientSlot] = []

    for json_file in sorted(sing_dir.glob("*.json")):
        try:
            data = json.loads(json_file.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        if data.get("enabled") is False or data.get("inUltimateSingularity") is False:
            if data.get("enabled") is False:
                continue

        sing_id = f"extendedcrafting:{json_file.stem}"
        ing_obj = data.get("ingredient")
        mat_count = int(data.get("materialCount", 5000))
        slot = build_slot(ing_obj, slot_key="input")
        if not slot:
            continue
        slot.count = mat_count

        sing_stack = RecipeStack(
            resource_id="extendedcrafting:singularity",
            count=1,
            nbt={"Id": sing_id},
        )

        recipes.append(
            NormalizedRecipe(
                recipe_id=f"extendedcrafting:compressor/{json_file.stem}_singularity",
                recipe_type="extendedcrafting:compressor",
                source_mod="extendedcrafting",
                data_source=DataSource.MOD_CONFIG,
                source_path=str(json_file),
                outputs=[sing_stack],
                inputs=[slot],
                machine_info=MachineInfo(
                    station_id="extendedcrafting:compressor",
                    station_name="Quantum Compressor",
                    energy_fe=int(data.get("powerRequired", 5000000)),
                ),
                extra_data={"singularity_id": sing_id, "material_count": mat_count},
            )
        )

        if data.get("inUltimateSingularity", True):
            ultimate_inputs.append(
                IngredientSlot(
                    alternatives=[
                        RecipeStack(
                            resource_id="extendedcrafting:singularity",
                            count=1,
                            nbt={"Id": sing_id},
                        )
                    ],
                    count=1,
                )
            )

    if ultimate_inputs:
        recipes.append(
            NormalizedRecipe(
                recipe_id="extendedcrafting:ultimate_singularity",
                recipe_type="avaritia:extreme_craft",
                source_mod="extendedcrafting",
                data_source=DataSource.MOD_CONFIG,
                source_path=str(sing_dir),
                outputs=[RecipeStack("extendedcrafting:ultimate_singularity", 1)],
                inputs=ultimate_inputs,
                machine_info=MachineInfo(
                    station_id="extendedcrafting:crafting_table",
                    station_name="Ultimate Crafting Table (9x9)",
                ),
            )
        )

    return recipes


def parse_hnn_data_models(kubejs_data_dir: Path) -> list[NormalizedRecipe]:
    """Generate Simulation Chamber and Loot Fabricator recipes from kubejs/data/hostilenetworks/data_models/*.json."""
    models_dir = kubejs_data_dir / "hostilenetworks" / "data_models"
    if not models_dir.exists():
        return []

    recipes: list[NormalizedRecipe] = []
    for json_file in sorted(models_dir.rglob("*.json")):
        try:
            data = json.loads(json_file.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            continue
        if not isinstance(data, dict) or "entity" not in data:
            continue

        rel_id = json_file.relative_to(models_dir).with_suffix("").as_posix()
        model_id = f"hostilenetworks:{rel_id}"
        sim_cost = int(data.get("sim_cost", 256))

        input_slot = build_slot(data.get("input", {"item": "hostilenetworks:prediction_matrix"}))
        if not input_slot:
            continue

        base_drop = parse_stack_Entry(data.get("base_drop"))
        pred_stack = RecipeStack(
            resource_id="hostilenetworks:prediction",
            count=1,
            nbt={"data_model": {"id": model_id}},
        )
        sim_outputs = [pred_stack]
        if base_drop:
            base_drop[0].is_primary = False
            sim_outputs.append(base_drop[0])

        model_catalyst = IngredientSlot(
            alternatives=[
                RecipeStack(
                    resource_id="hostilenetworks:data_model",
                    count=1,
                    nbt={"data_model": {"id": model_id}},
                )
            ],
            count=1,
            consumable=False,
            slot_key="data_model",
        )

        recipes.append(
            NormalizedRecipe(
                recipe_id=f"hostilenetworks:simulation/{rel_id}",
                recipe_type="hostilenetworks:sim_chamber",
                source_mod="hostilenetworks",
                data_source=DataSource.MOD_CONFIG,
                source_path=str(json_file),
                outputs=sim_outputs,
                inputs=[model_catalyst, input_slot],
                machine_info=MachineInfo(
                    station_id="hostilenetworks:sim_chamber",
                    station_name="Simulation Chamber",
                    energy_fe=sim_cost * 300,
                    ticks=300,
                ),
            )
        )

        # Loot Fabricator drops
        for idx, drop in enumerate(data.get("fabricator_drops", [])):
            drop_stacks = parse_stack_Entry(drop)
            if not drop_stacks:
                continue
            drop_st = drop_stacks[0]
            recipes.append(
                NormalizedRecipe(
                    recipe_id=f"hostilenetworks:loot_fabricator/{rel_id}_{idx}",
                    recipe_type="hostilenetworks:loot_fabricator",
                    source_mod="hostilenetworks",
                    data_source=DataSource.MOD_CONFIG,
                    source_path=str(json_file),
                    outputs=[drop_st],
                    inputs=[
                        IngredientSlot(
                            alternatives=[
                                RecipeStack(
                                    resource_id="hostilenetworks:prediction",
                                    count=1,
                                    nbt={"data_model": {"id": model_id}},
                                )
                            ],
                            count=1,
                        )
                    ],
                    machine_info=MachineInfo(
                        station_id="hostilenetworks:loot_fabricator",
                        station_name="Loot Fabricator",
                    ),
                )
            )

    return recipes


@dataclass
class KubeJSScriptAnalysisResult:
    """Aggregated recipes, removals, and replacements extracted from KubeJS server_scripts."""

    added_recipes: list[NormalizedRecipe] = field(default_factory=list)
    removal_filters: list[RemovalFilter] = field(default_factory=list)
    replacement_rules: list[ReplacementRule] = field(default_factory=list)
    parse_warnings: list[str] = field(default_factory=list)


_HELPER_NAMES = (
    "shapeless",
    "shapelessdraconic",
    "reverseshapelessdraconic",
    "shapelessdraconicadditions",
    "reverseshapelessdraconicadditions",
    "create323",
    "create_conduit_craft",
    "create_conduit_craft2",
    "create2x2",
    "create2x2same",
    "create3x3",
    "create3x3_EV_EX",
    "create3x3same",
    "seedtiercrafting1",
    "seedtiercrafting2",
    "seedtiercrafting2extra",
    "seedtiermobcrafting2",
    "create3x3jetpack",
)


def _parse_filter_object(filter_expr: str) -> list[RemovalFilter]:
    """Parse a KubeJS filter expression like `{ output: 'x', type: 'y' }` or `[{...}]`."""
    cleaned = filter_expr.strip()
    if cleaned.startswith("[") and cleaned.endswith("]"):
        inner_items = split_top_level_args(cleaned[1:-1])
        res: list[RemovalFilter] = []
        for it in inner_items:
            res.extend(_parse_filter_object(it))
        return res

    if not cleaned.startswith("{"):
        return []

    rf = RemovalFilter()
    id_m = re.search(r"\bid\s*:\s*['\"]([^'\"]+)['\"]", cleaned)
    if id_m and id_m.group(1).strip():
        rf.recipe_id = id_m.group(1).strip()

    mod_m = re.search(r"\bmod\s*:\s*['\"]([^'\"]+)['\"]", cleaned)
    if mod_m and mod_m.group(1).strip():
        rf.mod = mod_m.group(1).strip()

    type_m = re.search(r"\btype\s*:\s*['\"]([^'\"]+)['\"]", cleaned)
    if type_m and type_m.group(1).strip():
        rf.recipe_type = type_m.group(1).strip()

    out_regex_m = re.search(r"\boutput\s*:\s*/([^/]+)/", cleaned)
    if out_regex_m:
        rf.output_regex = re.compile(out_regex_m.group(1))
    else:
        out_m = re.search(r"\boutput\s*:\s*(?:\[\s*)?['\"]([^'\"]+)['\"]", cleaned)
        if out_m and out_m.group(1).strip():
            rf.output = out_m.group(1).strip()

    in_m = re.search(r"\binput\s*:\s*(?:\[\s*)?['\"]([^'\"]+)['\"]", cleaned)
    if in_m and in_m.group(1).strip():
        rf.input_item = in_m.group(1).strip()

    return [rf]


def parse_kubejs_server_scripts(
    server_scripts_dir: Path,
    loaded_mods: set[str] | None = None,
    tag_registry: TagRegistry | None = None,
) -> KubeJSScriptAnalysisResult:
    """Scan all .js files in `kubejs/server_scripts` and extract removals, additions, and replacements."""
    result = KubeJSScriptAnalysisResult()
    if not server_scripts_dir or not server_scripts_dir.exists():
        return result

    helper_pattern = re.compile(
        r"(?<!function\s)\b(" + "|".join(_HELPER_NAMES) + r")\s*\("
    )

    for js_file in sorted(server_scripts_dir.rglob("*.js")):
        if js_file.name == "functions.js":
            continue
        try:
            raw_text = js_file.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            result.parse_warnings.append(f"Failed to read {js_file}: {exc}")
            continue

        rel_path = js_file.relative_to(server_scripts_dir.parent).as_posix()
        clean_text = strip_js_comments(raw_text)

        # 1. Masterful Machinery processes
        if "MMEvents.createProcesses" in clean_text:
            mm_recipes = parse_masterful_machinery_processes(clean_text, rel_path)
            result.added_recipes.extend(mm_recipes)

        if "ServerEvents.recipes" not in clean_text and "removeRecipebyOutput" not in clean_text:
            continue

        # 2. Extract array-based bulk removals (e.g. in remove_recipes.js and botanypots_remove.js)
        for arr_name, field_kind in (
            ("removeRecipebyOutput", "output"),
            ("removeRecipebyRecipeID", "id"),
            ("removeRecipebyType", "type"),
        ):
            arr_m = re.search(
                rf"const\s+{arr_name}\s*=\s*\[([\s\S]*?)\];",
                clean_text,
            )
            if arr_m:
                for item_str in re.findall(r"['\"]([^'\"]+)['\"]", arr_m.group(1)):
                    val = item_str.strip()
                    if not val:
                        continue
                    if field_kind == "output":
                        result.removal_filters.append(RemovalFilter(output=val))
                    elif field_kind == "id":
                        result.removal_filters.append(RemovalFilter(recipe_id=val))
                    elif field_kind == "type":
                        result.removal_filters.append(RemovalFilter(recipe_type=val))

        # Also check for array .forEach(id => event.remove({ id: id })) patterns (e.g. stonecutter / botanypots)
        for foreach_m in re.finditer(
            r"\[([\s\S]*?)\]\.forEach\s*\(\s*\(?[a-zA-Z0-9_]+\)?\s*=>\s*\{?\s*[a-zA-Z0-9_]+\.remove\s*\(\s*\{\s*(id|output|type)\s*:",
            clean_text,
        ):
            arr_body, kind = foreach_m.groups()
            for val in re.findall(r"['\"]([^'\"]+)['\"]", arr_body):
                val = val.strip()
                if not val:
                    continue
                if kind == "id":
                    result.removal_filters.append(RemovalFilter(recipe_id=val))
                elif kind == "output":
                    result.removal_filters.append(RemovalFilter(output=val))
                elif kind == "type":
                    result.removal_filters.append(RemovalFilter(recipe_type=val))

        # 3. Direct event.remove(...) calls
        for rem_m in re.finditer(r"\b(?:event|e|r)\.remove\s*\(", clean_text):
            paren_str, _ = extract_balanced_block(clean_text, rem_m.end() - 1, "(", ")")
            if not paren_str:
                continue
            arg_inner = paren_str[1:-1].strip()
            result.removal_filters.extend(_parse_filter_object(arg_inner))

        # 4. Direct event.replaceInput(...) and event.replaceOutput(...) calls
        for rep_m in re.finditer(r"\b(?:event|e|r)\.(replaceInput|replaceOutput)\s*\(", clean_text):
            rep_kind = rep_m.group(1)
            paren_str, _ = extract_balanced_block(clean_text, rep_m.end() - 1, "(", ")")
            if not paren_str:
                continue
            args = split_top_level_args(paren_str[1:-1])
            if len(args) >= 3:
                filters = _parse_filter_object(args[0])
                filter_obj = filters[0] if filters else RemovalFilter()
                t_item = args[1].strip().strip("'\"")
                r_item = args[2].strip().strip("'\"")
                if t_item and r_item:
                    result.replacement_rules.append(
                        ReplacementRule(
                            is_output=(rep_kind == "replaceOutput"),
                            filter_criteria=filter_obj,
                            target_item=t_item,
                            replacement_item=r_item,
                        )
                    )

        # 5. event.custom({...}) calls
        for idx, cust_m in enumerate(re.finditer(r"\b(?:event|e|r)\.custom\s*\(", clean_text)):
            paren_str, end_pos = extract_balanced_block(clean_text, cust_m.end() - 1, "(", ")")
            if not paren_str:
                continue
            obj_str, _ = extract_balanced_block(paren_str, 0, "{", "}")
            if not obj_str:
                continue
            py_obj = js_object_to_python(obj_str)
            if not isinstance(py_obj, dict):
                result.parse_warnings.append(f"Could not parse .custom() object in {rel_path}")
                continue

            # Check chained .id('...') right after .custom(...)
            tail_slice = clean_text[end_pos : end_pos + 120]
            id_chain = re.match(r"^\s*\.id\s*\(\s*['\"]([^'\"]+)['\"]\s*\)", tail_slice)
            if id_chain:
                custom_id = id_chain.group(1)
            else:
                custom_id = _make_kubejs_recipe_id("custom", str(py_obj.get("type", "recipe")), rel_path, idx)

            parsed_rec, _ = parse_recipe_json(
                recipe_id=custom_id,
                data=py_obj,
                data_source=DataSource.KUBEJS_SCRIPT,
                source_path=rel_path,
                loaded_mods=loaded_mods,
                tag_registry=tag_registry,
            )
            if parsed_rec:
                result.added_recipes.append(parsed_rec)

        # 6. Helper function calls from functions.js (create3x3, create3x3same, seedtiercrafting*, shapeless, etc.)
        for idx, h_m in enumerate(helper_pattern.finditer(clean_text)):
            h_name = h_m.group(1)
            # Skip event.shapeless(...) which has '.' before shapeless
            if h_m.start() > 0 and clean_text[h_m.start() - 1] == ".":
                continue
            paren_str, _ = extract_balanced_block(clean_text, h_m.end() - 1, "(", ")")
            if not paren_str:
                continue
            args = split_top_level_args(paren_str[1:-1])
            if len(args) < 2:
                continue
            # args[0] is `event`, args[1] is `output`, args[2] (optional) is `[inputs...]`
            out_stack = parse_js_item_expr(args[1])
            if not out_stack:
                continue
            in_stacks: list[RecipeStack] = []
            if len(args) >= 3:
                arr_expr = args[2].strip()
                if arr_expr.startswith("[") and arr_expr.endswith("]"):
                    for elem_expr in split_top_level_args(arr_expr[1:-1]):
                        st = parse_js_item_expr(elem_expr)
                        if st:
                            in_stacks.append(st)
                else:
                    st = parse_js_item_expr(arr_expr)
                    if st:
                        in_stacks.append(st)

            rec_id = _make_kubejs_recipe_id(h_name, out_stack.resource_id, rel_path, idx)
            rec = _expand_helper_call(h_name, out_stack, in_stacks, rec_id, rel_path)
            if rec:
                result.added_recipes.append(rec)

        # 7. Direct event.shaped / event.shapeless / event.smelting / event.blasting / event.stonecutting / event.smithing
        for idx, std_m in enumerate(
            re.finditer(
                r"\b(?:event|e|r)\.(shaped|shapeless|smelting|blasting|stonecutting|smithing)\s*\(",
                clean_text,
            )
        ):
            method = std_m.group(1)
            paren_str, end_pos = extract_balanced_block(clean_text, std_m.end() - 1, "(", ")")
            if not paren_str:
                continue
            args = split_top_level_args(paren_str[1:-1])
            if len(args) < 2:
                continue

            out_stack = parse_js_item_expr(args[0])
            if not out_stack:
                continue

            tail_slice = clean_text[end_pos : end_pos + 120]
            id_chain = re.match(r"^\s*\.id\s*\(\s*['\"]([^'\"]+)['\"]\s*\)", tail_slice)
            rec_id = (
                normalize_identifier(id_chain.group(1))
                if id_chain
                else _make_kubejs_recipe_id(method, out_stack.resource_id, rel_path, idx)
            )

            if method == "shaped" and len(args) >= 3:
                pat_py = js_object_to_python(args[1])
                key_py = js_object_to_python(args[2])
                if isinstance(pat_py, list) and isinstance(key_py, dict):
                    synth = {
                        "type": "minecraft:crafting_shaped",
                        "pattern": pat_py,
                        "key": key_py,
                        "result": {"item": out_stack.resource_id, "count": out_stack.count},
                    }
                    parsed_rec, _ = parse_recipe_json(
                        rec_id, synth, DataSource.KUBEJS_SCRIPT, rel_path, loaded_mods, tag_registry
                    )
                    if parsed_rec:
                        result.added_recipes.append(parsed_rec)

            elif method == "shapeless":
                in_slots: list[IngredientSlot] = []
                rhs = args[1].strip()
                elem_exprs = split_top_level_args(rhs[1:-1]) if (rhs.startswith("[") and rhs.endswith("]")) else [rhs]
                for expr in elem_exprs:
                    st = parse_js_item_expr(expr)
                    if st:
                        in_slots.append(
                            IngredientSlot(
                                alternatives=[RecipeStack(st.resource_id, 1, st.resource_type, st.nbt)],
                                count=st.count,
                            )
                        )
                if in_slots:
                    result.added_recipes.append(
                        NormalizedRecipe(
                            recipe_id=rec_id,
                            recipe_type="minecraft:crafting_shapeless",
                            source_mod="kubejs",
                            data_source=DataSource.KUBEJS_SCRIPT,
                            source_path=rel_path,
                            outputs=[out_stack],
                            inputs=in_slots,
                            machine_info=MachineInfo("minecraft:crafting_table", "Crafting Table"),
                        )
                    )

            elif method in ("smelting", "blasting", "stonecutting"):
                in_st = parse_js_item_expr(args[1])
                if in_st:
                    r_type = f"minecraft:{method}"
                    station = (
                        ("minecraft:furnace", "Furnace")
                        if method == "smelting"
                        else (
                            ("minecraft:blast_furnace", "Blast Furnace")
                            if method == "blasting"
                            else ("minecraft:stonecutter", "Stonecutter")
                        )
                    )
                    result.added_recipes.append(
                        NormalizedRecipe(
                            recipe_id=rec_id,
                            recipe_type=r_type,
                            source_mod="kubejs",
                            data_source=DataSource.KUBEJS_SCRIPT,
                            source_path=rel_path,
                            outputs=[out_stack],
                            inputs=[
                                IngredientSlot(
                                    alternatives=[RecipeStack(in_st.resource_id, 1, in_st.resource_type, in_st.nbt)],
                                    count=in_st.count,
                                )
                            ],
                            machine_info=MachineInfo(station[0], station[1]),
                        )
                    )

    return result

