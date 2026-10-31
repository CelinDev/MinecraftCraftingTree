"""Graph dependency engine for recursive crafting trees, cycle detection, and material consolidation."""

from __future__ import annotations

import math
from typing import Callable

from backend.engine.models import (
    ConsolidatedMaterial,
    CraftingStep,
    CraftingTreeResult,
    DependencyNode,
    NodeStatus,
)
from backend.importer.tags import TagRegistry
from backend.models.recipe import (
    NormalizedRecipe,
    RecipeStack,
    ResourceType,
    ValidationStatus,
    normalize_identifier,
)

BASIC_RESOURCES = {
    # Stones & earth
    "minecraft:cobblestone", "minecraft:stone", "minecraft:deepslate", "minecraft:cobbled_deepslate",
    "minecraft:dirt", "minecraft:sand", "minecraft:gravel", "minecraft:clay", "minecraft:clay_ball",
    "minecraft:flint", "minecraft:andesite", "minecraft:diorite", "minecraft:granite", "minecraft:obsidian",
    "minecraft:netherrack", "minecraft:end_stone", "minecraft:tuff", "minecraft:calcite",
    "minecraft:blackstone", "minecraft:basalt", "minecraft:soul_sand", "minecraft:soul_soil",
    "forge:cobblestone", "forge:stone", "forge:sand", "forge:gravel", "forge:obsidian",
    # Logs & wood
    "minecraft:oak_log", "minecraft:birch_log", "minecraft:spruce_log", "minecraft:jungle_log",
    "minecraft:acacia_log", "minecraft:dark_oak_log", "minecraft:mangrove_log", "minecraft:cherry_log",
    "#minecraft:logs", "#forge:logs",
    # Fluids & basic gases
    "minecraft:water", "minecraft:water_bucket", "minecraft:lava", "minecraft:lava_bucket",
    "mekanism:oxygen", "forge:oxygen", "mekanism:hydrogen",
    # Ores & raw
    "minecraft:raw_iron", "minecraft:raw_gold", "minecraft:raw_copper", "minecraft:coal", "minecraft:charcoal",
    "minecraft:redstone", "minecraft:lapis_lazuli", "minecraft:diamond", "minecraft:emerald", "minecraft:quartz",
    "forge:gems/diamond", "forge:gems/emerald", "forge:gems/quartz", "forge:dusts/redstone",
    # Basic drops & farming
    "minecraft:wheat", "minecraft:wheat_seeds", "minecraft:sugar_cane", "minecraft:bamboo", "minecraft:cactus",
    "minecraft:leather", "minecraft:string", "minecraft:feather", "minecraft:bone", "minecraft:gunpowder",
    "minecraft:slime_ball", "minecraft:ender_pearl", "minecraft:blaze_rod", "minecraft:egg",
    "forge:string", "forge:leather", "forge:ender_pearls", "forge:bones", "forge:slimeballs",
    # Base essences & special drops
    "mysticalagriculture:prosperity_shard", "mysticalagriculture:inferium_essence",
    "bloodmagic:hellforgedparts",
}


def is_basic_raw(item_key: str) -> bool:
    """Check whether an item is a fundamental world resource that should not be recursively expanded."""
    clean = item_key.strip().lstrip("#")
    if clean in BASIC_RESOURCES or f"#{clean}" in BASIC_RESOURCES:
        return True
    if clean.endswith("_log") or clean.endswith("_wood") or clean.endswith("_stem") or clean.endswith("_hyphae"):
        return True
    if clean.startswith("forge:ores/") or clean.startswith("forge:raw_materials/"):
        return True
    # If a compressium block is required in an advanced recipe, do not unpack it into billions of base items
    if clean.startswith("compressium:"):
        return True
    return False


def is_unpacking_or_compressium(r: NormalizedRecipe, target_key: str) -> bool:
    """Check if a recipe is a decompression / uncrafting shortcut or extreme bulk conversion."""
    # 1. Unpacking / decompression recipes
    if "_uncraft" in r.recipe_id or "uncompress" in r.recipe_id or "_from_block" in r.recipe_id:
        return True
    # 2. Block compressium shortcuts from being used as normal crafting recipes for non-compressium items
    # (e.g. mm:coal_to_hellforged_parts using compressium:coal_2 x344064)
    if not (target_key.startswith("compressium:") or "singularity" in target_key or "slate" in target_key or "cyclic:" in target_key):
        for s in r.inputs:
            for alt in s.alternatives:
                if alt.resource_id.startswith("compressium:"):
                    return True
    # 3. Block to 4 or 9 ingots/gems uncrafting
    if len(r.inputs) == 1:
        inp_id = r.inputs[0].alternatives[0].resource_id if r.inputs[0].alternatives else ""
        out = r.outputs[0] if r.outputs else None
        if out and out.count in (4, 9):
            if inp_id.endswith("_block") or "block" in inp_id or "storage_blocks" in inp_id:
                return True
        if out and out.count == 9 and not target_key.endswith("_nugget"):
            return True
    # 4. Outrageous item count (> 1000 items per craft for non-fluids)
    for s in r.inputs:
        if s.count > 1000 and not any(k in s.alternatives[0].resource_id for k in ("water", "lava", "fluid", "gas", "antimatter", "energy")):
            return True
    return False


def is_essence_or_mystical_cross_recipe(r: NormalizedRecipe, target_key: str) -> bool:
    """Check if a recipe is an essence crafting shortcut from Mystical Agriculture for an item of another mod."""
    clean = target_key.strip().lstrip("#")
    target_mod = clean.split(":")[0] if ":" in clean else ""
    # If the user is specifically inspecting an item from Mystical Agriculture, allow it!
    if target_mod in ("mysticalagriculture", "mysticalagradditions", "mysticalcustomization"):
        return False

    # Check if recipe comes from Mystical Agriculture or its addons
    if r.source_mod in ("mysticalagriculture", "mysticalagradditions", "mysticalcustomization"):
        return True
    if any(m in r.recipe_id for m in (
        "mysticalagriculture:essence",
        "mysticalagradditions:essence",
        "mysticalcustomization:",
    )):
        return True

    # Check if all or majority inputs are essences
    for slot in r.inputs:
        for alt in slot.alternatives:
            if "essence" in alt.resource_id and ("mystical" in alt.resource_id or "inferium" in alt.resource_id):
                return True
    return False


class DependencyEngine:
    """Engine responsible for resolving recipes, expanding crafting trees, and consolidating production."""

    def __init__(
        self,
        recipes: dict[str, NormalizedRecipe],
        tag_registry: TagRegistry | None = None,
    ) -> None:
        self.recipes = recipes
        self.tag_registry = tag_registry or TagRegistry()
        self._output_index: dict[str, list[NormalizedRecipe]] = {}
        self._build_output_index()

    def _build_output_index(self) -> None:
        """Index all active valid/partial recipes by their primary output item_key and resource_id."""
        self._output_index.clear()
        for rec in self.recipes.values():
            if rec.validation_status in (ValidationStatus.REMOVED, ValidationStatus.INVALID):
                continue
            for out in rec.outputs:
                key = out.item_key
                self._output_index.setdefault(key, []).append(rec)
                # Also index by plain resource_id without NBT for fuzzy queries
                if out.nbt and out.resource_id != key:
                    self._output_index.setdefault(out.resource_id, []).append(rec)

    def find_recipes_for_item(self, item_or_tag: str) -> list[NormalizedRecipe]:
        """Find all known recipes producing the given item, tag, or canonical key."""
        clean = item_or_tag.strip()
        norm = normalize_identifier(clean.lstrip("#"))

        # If it's a tag, resolve concrete items first or search directly
        if clean.startswith("#"):
            concrete = self.tag_registry.get_tag_items(norm)
            results: list[NormalizedRecipe] = []
            for c in concrete:
                for r in self._output_index.get(c, []):
                    if r not in results:
                        results.append(r)
            return results

        # Direct search by canonical key or resource_id
        if clean in self._output_index:
            return list(self._output_index[clean])
        if norm in self._output_index:
            return list(self._output_index[norm])
        return []

    def build_crafting_tree(
        self,
        target_item: str,
        target_count: float | int = 1,
        selected_recipes: dict[str, str] | None = None,
        recipe_selector: Callable[[str, list[NormalizedRecipe]], NormalizedRecipe | None] | None = None,
        max_depth: int = 50,
        prune_basic: bool = True,
        avoid_mystical_agriculture: bool = True,
    ) -> CraftingTreeResult:
        """
        Build an interactive recursive crafting tree for `target_item`.

        - `target_item`: Item ID, tag or canonical key (e.g. 'minecraft:iron_ingot' or '#forge:ingots/iron').
        - `target_count`: Desired final output quantity.
        - `selected_recipes`: User-chosen recipe overrides {item_key: recipe_id}.
        - `recipe_selector`: Optional heuristic selector when no override is given.
        - `max_depth`: Safety cutoff against runaway branch expansion.
        - `prune_basic`: When True, treats fundamental raw resources (wood, cobblestone, ores) as base leaves.
        - `avoid_mystical_agriculture`: When True, avoids Mystical Agriculture essence shortcuts for items of other mods.
        """
        selected_recipes = selected_recipes or {}
        has_cycle_flag = [False]
        has_incomplete_flag = [False]
        node_counter = [0]

        # Resolve tag to preferred concrete item if necessary
        clean_target = target_item.strip()
        if clean_target.startswith("#"):
            pref = self.tag_registry.get_preferred_item(clean_target[1:])
            resolved_key = pref if pref else clean_target
        else:
            resolved_key = normalize_identifier(clean_target)

        def _expand(
            item_key: str,
            needed_count: float | int,
            current_path: list[str],
            depth: int,
            is_catalyst_node: bool = False,
        ) -> DependencyNode:
            node_counter[0] += 1
            node_id = f"node_{node_counter[0]}_{item_key.replace(':', '_').replace('#', 'tag_')}"

            available = self.find_recipes_for_item(item_key)

            # Prune basic raw items when not the root target itself
            if prune_basic and depth > 0 and is_basic_raw(item_key):
                return DependencyNode(
                    node_id=node_id,
                    item_key=item_key,
                    resource_id=item_key.split("{")[0].lstrip("#"),
                    resource_type=ResourceType.TAG if item_key.startswith("#") else ResourceType.ITEM,
                    count=needed_count,
                    status=NodeStatus.RAW_MATERIAL,
                    available_recipes=available,
                    depth=depth,
                    is_catalyst=is_catalyst_node,
                )

            # Check cycle along current path
            if item_key in current_path:
                has_cycle_flag[0] = True
                return DependencyNode(
                    node_id=node_id,
                    item_key=item_key,
                    resource_id=item_key.split("{")[0].lstrip("#"),
                    resource_type=ResourceType.TAG if item_key.startswith("#") else ResourceType.ITEM,
                    count=needed_count,
                    status=NodeStatus.CIRCULAR_DEPENDENCY,
                    depth=depth,
                    is_catalyst=is_catalyst_node,
                    warning=f"Circular crafting dependency detected on {item_key}",
                )

            if depth >= max_depth:
                return DependencyNode(
                    node_id=node_id,
                    item_key=item_key,
                    resource_id=item_key.split("{")[0].lstrip("#"),
                    resource_type=ResourceType.ITEM,
                    count=needed_count,
                    status=NodeStatus.RAW_MATERIAL,
                    depth=depth,
                    is_catalyst=is_catalyst_node,
                    warning=f"Max tree depth ({max_depth}) reached; treated as raw material",
                )

            if not available or is_catalyst_node:
                # No recipe known or is non-consumed catalyst -> base gatherable resource / catalyst
                return DependencyNode(
                    node_id=node_id,
                    item_key=item_key,
                    resource_id=item_key.split("{")[0].lstrip("#"),
                    resource_type=ResourceType.TAG if item_key.startswith("#") else ResourceType.ITEM,
                    count=needed_count,
                    status=NodeStatus.CATALYST if is_catalyst_node else NodeStatus.RAW_MATERIAL,
                    available_recipes=available,
                    depth=depth,
                    is_catalyst=is_catalyst_node,
                )

            # Determine which recipe to select
            chosen: NormalizedRecipe | None = None
            if item_key in selected_recipes:
                chosen_id = normalize_identifier(selected_recipes[item_key])
                chosen = next(
                    (r for r in available if r.recipe_id == chosen_id or r.recipe_id.endswith(f":{chosen_id}")),
                    None,
                )

            if chosen is None and recipe_selector:
                chosen = recipe_selector(item_key, available)

            if chosen is None:
                chosen = self._default_recipe_heuristic(
                    item_key,
                    available,
                    current_path,
                    avoid_mystical_agriculture=avoid_mystical_agriculture,
                )

            if chosen is None:
                # No acceptable default recipe found (e.g. only extreme bulk shortcuts exist) -> treat as raw
                return DependencyNode(
                    node_id=node_id,
                    item_key=item_key,
                    resource_id=item_key.split("{")[0].lstrip("#"),
                    resource_type=ResourceType.TAG if item_key.startswith("#") else ResourceType.ITEM,
                    count=needed_count,
                    status=NodeStatus.RAW_MATERIAL,
                    available_recipes=available,
                    depth=depth,
                    is_catalyst=is_catalyst_node,
                )

            if chosen.validation_status in (
                ValidationStatus.PARTIAL,
                ValidationStatus.UNSUPPORTED,
            ):
                has_incomplete_flag[0] = True

            # Calculate batches/runs needed
            primary_out = chosen.primary_output if chosen else None
            output_per_batch = primary_out.count if primary_out else 1
            if output_per_batch <= 0:
                output_per_batch = 1

            # Catalysts only need 1 unit regardless of batches
            if is_catalyst_node:
                runs = 1
                produced = 1
                excess = 0
            else:
                runs = max(1, math.ceil(needed_count / output_per_batch))
                produced = runs * output_per_batch
                excess = produced - needed_count

            status = NodeStatus.CRAFTABLE
            if len(available) > 1:
                status = NodeStatus.ALTERNATIVE_AVAILABLE
            if chosen and chosen.validation_status != ValidationStatus.VALID:
                status = NodeStatus.INCOMPLETE_RECIPE

            node = DependencyNode(
                node_id=node_id,
                item_key=item_key,
                resource_id=item_key.split("{")[0].lstrip("#"),
                resource_type=ResourceType.ITEM,
                count=needed_count,
                status=status,
                selected_recipe=chosen,
                available_recipes=available,
                depth=depth,
                runs_needed=runs,
                produced_count=produced,
                excess_count=excess,
                is_catalyst=is_catalyst_node,
            )

            next_path = current_path + [item_key]
            if chosen:
                for slot in chosen.inputs:
                    if not slot.alternatives:
                        continue
                    # Pick best alternative in slot
                    alt = self._pick_slot_alternative(slot.alternatives)
                    slot_mult = 1 if not slot.consumable else runs
                    sub_count = slot.count * slot_mult

                    # If this input is already present earlier in the active path, mark it as cycle leaf
                    # rather than expanding its children repeatedly
                    if alt.item_key in next_path:
                        has_cycle_flag[0] = True
                        node_counter[0] += 1
                        cycle_leaf = DependencyNode(
                            node_id=f"node_{node_counter[0]}_{alt.item_key.replace(':', '_').replace('#', 'tag_')}",
                            item_key=alt.item_key,
                            resource_id=alt.resource_id,
                            resource_type=alt.resource_type,
                            count=sub_count,
                            status=NodeStatus.CIRCULAR_DEPENDENCY,
                            depth=depth + 1,
                            is_catalyst=(not slot.consumable),
                            warning=f"Circular crafting dependency detected on {alt.item_key}",
                        )
                        node.children.append(cycle_leaf)
                        continue

                    child_node = _expand(
                        item_key=alt.item_key,
                        needed_count=sub_count,
                        current_path=next_path,
                        depth=depth + 1,
                        is_catalyst_node=(not slot.consumable),
                    )
                    node.children.append(child_node)

            return node

        root = _expand(resolved_key, target_count, [], 0)

        # Post-traversal: collect concrete crafting steps and consolidate raw materials
        steps, raw_mats, catalysts, byproducts = self._consolidate_tree(root)

        return CraftingTreeResult(
            target_item_key=resolved_key,
            target_count=target_count,
            root_node=root,
            steps=steps,
            raw_materials=raw_mats,
            catalysts=catalysts,
            byproducts=byproducts,
            has_circular_dependency=has_cycle_flag[0],
            has_incomplete_recipes=has_incomplete_flag[0],
        )

    def _default_recipe_heuristic(
        self,
        target_key: str,
        available: list[NormalizedRecipe],
        current_path: list[str],
        avoid_mystical_agriculture: bool = True,
    ) -> NormalizedRecipe | None:
        """Pick the most straightforward valid recipe avoiding decompression, compressium, mystical bypasses and reciprocal cycles."""
        valid_recs = [r for r in available if r.validation_status == ValidationStatus.VALID]
        candidates = valid_recs if valid_recs else available

        # Filter out unpacking/compressium shortcuts
        candidates = [r for r in candidates if not is_unpacking_or_compressium(r, target_key)]
        if not candidates:
            return None

        clean_target = target_key.strip().lstrip("#")
        target_mod = clean_target.split(":")[0] if ":" in clean_target else ""

        # Filter out Mystical Agriculture essence bypasses when target is from another mod
        if avoid_mystical_agriculture:
            non_mystical = [r for r in candidates if not is_essence_or_mystical_cross_recipe(r, target_key)]
            if non_mystical:
                candidates = non_mystical

        def _score(r: NormalizedRecipe) -> int:
            score = 100

            # Favor native mod recipes (e.g. Powah recipe for Powah crystal)
            if target_mod and r.source_mod == target_mod:
                score += 50

            # Heavily penalize cross-mod Mystical Agriculture essence recipes
            if avoid_mystical_agriculture and is_essence_or_mystical_cross_recipe(r, target_key):
                score -= 300

            # Penalize recipes requiring an item already in current_path
            for slot in r.inputs:
                for alt in slot.alternatives:
                    if alt.item_key in current_path:
                        score -= 60

            # If crafting an ingot, prefer smelting from raw material or ore over crafting from nuggets
            if target_key.endswith("_ingot"):
                if r.recipe_type in ("minecraft:smelting", "minecraft:blasting"):
                    for slot in r.inputs:
                        for alt in slot.alternatives:
                            if "raw_" in alt.resource_id or "raw_materials" in alt.resource_id:
                                score += 90
                            elif "_ore" in alt.resource_id or "ores" in alt.resource_id:
                                score += 70
                # Penalize crafting ingot from nuggets (9 nuggets -> 1 ingot)
                if r.recipe_type in ("minecraft:crafting_shaped", "minecraft:crafting_shapeless"):
                    for slot in r.inputs:
                        for alt in slot.alternatives:
                            if "nugget" in alt.resource_id:
                                score -= 50

            # Prefer shaped/shapeless crafting table
            if r.recipe_type in ("minecraft:crafting_shaped", "minecraft:crafting_shapeless"):
                score += 25
            elif r.recipe_type in ("minecraft:smelting", "minecraft:blasting"):
                score += 20

            # Penalize recipes with missing/zero inputs
            if not r.inputs:
                score -= 30
            return score

        candidates.sort(key=_score, reverse=True)
        return candidates[0]

    def _pick_slot_alternative(self, alternatives: list[RecipeStack]) -> RecipeStack:
        """Choose the best item/tag from an alternative slot according to Almost Unified preferences."""
        for alt in alternatives:
            if alt.resource_type == ResourceType.TAG:
                pref = self.tag_registry.get_preferred_item(alt.resource_id)
                if pref:
                    return RecipeStack(resource_id=pref, count=alt.count, nbt=alt.nbt)
            return alt
        return alternatives[0]

    def _consolidate_tree(
        self, root: DependencyNode
    ) -> tuple[
        list[CraftingStep],
        list[ConsolidatedMaterial],
        list[ConsolidatedMaterial],
        list[RecipeStack],
    ]:
        """Traverse tree post-order to build sequential crafting steps and aggregate raw materials without double-counting."""
        steps: list[CraftingStep] = []
        raw_map: dict[str, ConsolidatedMaterial] = {}
        catalyst_map: dict[str, ConsolidatedMaterial] = {}
        byproduct_map: dict[str, RecipeStack] = {}
        step_idx = [0]

        def _traverse(node: DependencyNode) -> None:
            for child in node.children:
                _traverse(child)

            if node.status in (
                NodeStatus.RAW_MATERIAL,
                NodeStatus.CATALYST,
                NodeStatus.CIRCULAR_DEPENDENCY,
            ):
                key = node.item_key
                if node.is_catalyst or node.status == NodeStatus.CATALYST:
                    if key not in catalyst_map:
                        catalyst_map[key] = ConsolidatedMaterial(
                            item_key=key,
                            resource_id=node.resource_id,
                            resource_type=node.resource_type,
                            total_needed=node.count,
                            is_catalyst=True,
                        )
                    else:
                        catalyst_map[key].total_needed = max(
                            catalyst_map[key].total_needed, node.count
                        )
                else:
                    if key not in raw_map:
                        raw_map[key] = ConsolidatedMaterial(
                            item_key=key,
                            resource_id=node.resource_id,
                            resource_type=node.resource_type,
                            total_needed=node.count,
                            is_catalyst=False,
                        )
                    else:
                        raw_map[key].total_needed += node.count

            elif node.selected_recipe:
                rec = node.selected_recipe
                step_idx[0] += 1
                machine_name = rec.machine_info.station_name if rec.machine_info else None
                station_id = rec.machine_info.station_id if rec.machine_info else None

                step_inputs = []
                for child in node.children:
                    step_inputs.append(
                        RecipeStack(
                            resource_id=child.resource_id,
                            count=child.count,
                            resource_type=child.resource_type,
                        )
                    )

                step = CraftingStep(
                    step_id=f"step_{step_idx[0]}",
                    recipe_id=rec.recipe_id,
                    recipe_type=rec.recipe_type,
                    source_mod=rec.source_mod,
                    output=RecipeStack(
                        resource_id=node.resource_id,
                        count=node.produced_count,
                        resource_type=node.resource_type,
                    ),
                    runs_needed=node.runs_needed,
                    inputs=step_inputs,
                    machine_name=machine_name,
                    station_id=station_id,
                    depth=node.depth,
                )
                steps.append(step)

                # Track secondary outputs / byproducts if any
                for out in rec.outputs:
                    if not out.is_primary:
                        by_cnt = out.count * node.runs_needed
                        if out.item_key in byproduct_map:
                            byproduct_map[out.item_key].count += by_cnt
                        else:
                            byproduct_map[out.item_key] = RecipeStack(
                                resource_id=out.resource_id,
                                count=by_cnt,
                                resource_type=out.resource_type,
                                chance=out.chance,
                                is_primary=False,
                            )

        _traverse(root)

        return (
            steps,
            sorted(raw_map.values(), key=lambda m: m.total_needed, reverse=True),
            sorted(catalyst_map.values(), key=lambda c: c.item_key),
            list(byproduct_map.values()),
        )
