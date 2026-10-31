"""Data structures for crafting trees, dependency nodes, and consolidated material requirements."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

from backend.models.recipe import NormalizedRecipe, RecipeStack, ResourceType
from backend.storage.item_names import item_names


class NodeStatus(str, Enum):
    """Status of a node in the crafting tree."""

    CRAFTABLE = "craftable"                # Known recipe selected and can be expanded
    RAW_MATERIAL = "raw_material"          # No crafting recipe found; base gatherable resource
    ALTERNATIVE_AVAILABLE = "alternative"  # Has alternative recipes available for selection
    CIRCULAR_DEPENDENCY = "circular"      # Cycle detected along this path
    INCOMPLETE_RECIPE = "incomplete"      # Recipe is partial or unsupported
    CATALYST = "catalyst"                  # Non-consumed item/tool required for machine operation


@dataclass
class CraftingStep:
    """A concrete crafting step to produce an intermediate or final item in the plan."""

    step_id: str
    recipe_id: str
    recipe_type: str
    source_mod: str
    output: RecipeStack
    runs_needed: int
    inputs: list[RecipeStack]
    machine_name: str | None = None
    station_id: str | None = None
    depth: int = 0

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if self.output:
            d["output"]["display_name"] = item_names.get_display_name(self.output.resource_id)
        for inp in d.get("inputs", []):
            inp["display_name"] = item_names.get_display_name(inp.get("resource_id", ""))
        return d


@dataclass
class ConsolidatedMaterial:
    """Consolidated raw material or catalyst requirement across the entire crafting tree."""

    item_key: str
    resource_id: str
    resource_type: ResourceType
    total_needed: float | int
    is_catalyst: bool = False
    nbt: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_key": self.item_key,
            "resource_id": self.resource_id,
            "display_name": item_names.get_display_name(self.resource_id or self.item_key),
            "mod_name": item_names.format_mod_name(self.resource_id.split(":")[0] if ":" in self.resource_id else ""),
            "resource_type": self.resource_type.value,
            "total_needed": self.total_needed,
            "is_catalyst": self.is_catalyst,
            "nbt": self.nbt,
        }


@dataclass
class DependencyNode:
    """Represents a node in the recursive crafting tree."""

    node_id: str
    item_key: str
    resource_id: str
    resource_type: ResourceType
    count: float | int
    status: NodeStatus
    selected_recipe: NormalizedRecipe | None = None
    available_recipes: list[NormalizedRecipe] = field(default_factory=list)
    children: list[DependencyNode] = field(default_factory=list)
    depth: int = 0
    runs_needed: int = 1
    produced_count: float | int = 0
    excess_count: float | int = 0
    is_catalyst: bool = False
    warning: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "item_key": self.item_key,
            "resource_id": self.resource_id,
            "display_name": item_names.get_display_name(self.resource_id or self.item_key),
            "mod_name": item_names.format_mod_name(self.resource_id.split(":")[0] if ":" in self.resource_id else ""),
            "resource_type": self.resource_type.value,
            "count": self.count,
            "status": self.status.value,
            "selected_recipe_id": self.selected_recipe.recipe_id if self.selected_recipe else None,
            "station_id": self.selected_recipe.machine_info.station_id if (self.selected_recipe and self.selected_recipe.machine_info) else None,
            "station_name": self.selected_recipe.machine_info.station_name if (self.selected_recipe and self.selected_recipe.machine_info) else None,
            "available_recipes_count": len(self.available_recipes),
            "runs_needed": self.runs_needed,
            "produced_count": self.produced_count,
            "excess_count": self.excess_count,
            "is_catalyst": self.is_catalyst,
            "warning": self.warning,
            "depth": self.depth,
            "children": [child.to_dict() for child in self.children],
        }


@dataclass
class CraftingTreeResult:
    """Full crafting plan output containing root tree, steps, and consolidated materials."""

    target_item_key: str
    target_count: float | int
    root_node: DependencyNode
    steps: list[CraftingStep] = field(default_factory=list)
    raw_materials: list[ConsolidatedMaterial] = field(default_factory=list)
    catalysts: list[ConsolidatedMaterial] = field(default_factory=list)
    byproducts: list[RecipeStack] = field(default_factory=list)
    has_circular_dependency: bool = False
    has_incomplete_recipes: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_item_key": self.target_item_key,
            "target_display_name": item_names.get_display_name(self.target_item_key),
            "target_mod_name": item_names.format_mod_name(self.target_item_key.split(":")[0] if ":" in self.target_item_key else ""),
            "target_count": self.target_count,
            "root_node": self.root_node.to_dict(),
            "steps": [s.to_dict() for s in self.steps],
            "raw_materials": [m.to_dict() for m in self.raw_materials],
            "catalysts": [c.to_dict() for c in self.catalysts],
            "byproducts": [b.to_dict() for b in self.byproducts],
            "has_circular_dependency": self.has_circular_dependency,
            "has_incomplete_recipes": self.has_incomplete_recipes,
        }

