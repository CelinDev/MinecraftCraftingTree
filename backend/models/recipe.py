"""Standardized internal representation of Minecraft / Modpack recipes."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class ResourceType(str, Enum):
    """Types of resources that can participate in a recipe."""

    ITEM = "item"
    TAG = "tag"
    FLUID = "fluid"
    FLUID_TAG = "fluid_tag"
    GAS = "gas"
    CHEMICAL_TAG = "chemical_tag"
    ENERGY = "energy"


class DataSource(str, Enum):
    """Origin layer of the recipe data."""

    VANILLA_JAR = "vanilla_jar"
    MOD_JAR = "mod_jar"
    KUBEJS_DATAPACK = "kubejs_datapack"
    KUBEJS_SCRIPT = "kubejs_script"
    MOD_CONFIG = "mod_config"
    RUNTIME_DUMP = "runtime_dump"
    TEST_FIXTURE = "test_fixture"


class ValidationStatus(str, Enum):
    """Validation and interpretation state of a recipe."""

    VALID = "valid"
    PARTIAL = "partial"
    UNSUPPORTED = "unsupported"
    INVALID = "invalid"
    REMOVED = "removed"


def normalize_identifier(raw_id: str, default_namespace: str = "minecraft") -> str:
    """Ensure a resource identifier has an explicit namespace (e.g. 'minecraft:iron_ingot')."""
    if not raw_id:
        return ""
    cleaned = str(raw_id).strip()
    is_tag = cleaned.startswith("#")
    if is_tag:
        cleaned = cleaned[1:].strip()
    if ":" not in cleaned:
        cleaned = f"{default_namespace}:{cleaned}"
    return f"#{cleaned}" if is_tag else cleaned


def canonicalize_nbt(nbt: Any) -> str | None:
    """Convert an NBT dict or SNBT string into a canonical deterministic string."""
    if nbt is None or nbt == "" or nbt == {}:
        return None
    if isinstance(nbt, dict):
        return json.dumps(nbt, sort_keys=True, separators=(",", ":"))
    if isinstance(nbt, str):
        stripped = nbt.strip()
        if not stripped or stripped == "{}":
            return None
        try:
            parsed = json.loads(stripped)
            if isinstance(parsed, dict):
                return json.dumps(parsed, sort_keys=True, separators=(",", ":"))
        except Exception:
            pass
        return stripped
    return str(nbt)


def format_item_key(resource_id: str, nbt: Any = None) -> str:
    """Return a unique canonical key combining resource_id and optional NBT discriminator."""
    norm_id = normalize_identifier(resource_id)
    canon_nbt = canonicalize_nbt(nbt)
    if canon_nbt:
        return f"{norm_id}{canon_nbt}"
    return norm_id


@dataclass
class RecipeStack:
    """Represents a specific item, tag, fluid, gas, or energy amount."""

    resource_id: str
    count: float | int = 1
    resource_type: ResourceType = ResourceType.ITEM
    nbt: str | None = None
    chance: float = 1.0
    is_primary: bool = True

    def __post_init__(self) -> None:
        if self.resource_type in (ResourceType.TAG, ResourceType.FLUID_TAG, ResourceType.CHEMICAL_TAG):
            raw = self.resource_id.lstrip("#")
            self.resource_id = normalize_identifier(raw)
        elif self.resource_id.startswith("#"):
            self.resource_type = ResourceType.TAG
            self.resource_id = normalize_identifier(self.resource_id[1:])
        else:
            self.resource_id = normalize_identifier(self.resource_id)
        self.nbt = canonicalize_nbt(self.nbt)
        if isinstance(self.count, float) and self.count.is_integer():
            self.count = int(self.count)

    @property
    def item_key(self) -> str:
        """Return the full key including '#' for tags and canonical NBT if present."""
        prefix = "#" if self.resource_type in (ResourceType.TAG, ResourceType.FLUID_TAG, ResourceType.CHEMICAL_TAG) else ""
        base = f"{prefix}{self.resource_id}"
        if self.nbt:
            return f"{base}{self.nbt}"
        return base

    def to_dict(self) -> dict[str, Any]:
        return {
            "resource_id": self.resource_id,
            "item_key": self.item_key,
            "count": self.count,
            "resource_type": self.resource_type.value,
            "nbt": self.nbt,
            "chance": self.chance,
            "is_primary": self.is_primary,
        }


@dataclass
class IngredientSlot:
    """Represents a single input requirement of a recipe, supporting alternative ingredients."""

    alternatives: list[RecipeStack] = field(default_factory=list)
    count: float | int = 1
    consumable: bool = True
    chance: float = 1.0
    slot_key: str | None = None

    def __post_init__(self) -> None:
        if isinstance(self.count, float) and self.count.is_integer():
            self.count = int(self.count)
        if self.chance == 0.0:
            self.consumable = False

    def matches_id(self, target_id: str) -> bool:
        """Check whether any alternative in this slot matches the given item or tag ID."""
        norm_target = normalize_identifier(target_id.lstrip("#"))
        is_tag_query = target_id.startswith("#")
        for alt in self.alternatives:
            if is_tag_query and alt.resource_type in (ResourceType.TAG, ResourceType.FLUID_TAG, ResourceType.CHEMICAL_TAG):
                if alt.resource_id == norm_target:
                    return True
            elif not is_tag_query and alt.resource_id == norm_target:
                return True
        return False

    def to_dict(self) -> dict[str, Any]:
        return {
            "alternatives": [alt.to_dict() for alt in self.alternatives],
            "count": self.count,
            "consumable": self.consumable,
            "chance": self.chance,
            "slot_key": self.slot_key,
        }


@dataclass
class MachineInfo:
    """Metadata about the machine, crafting station, or multiblock required by the recipe."""

    station_id: str
    station_name: str | None = None
    structure_id: str | None = None
    energy_fe: int | None = None
    ticks: int | None = None
    tier: str | None = None
    extra_requirements: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.station_id:
            self.station_id = normalize_identifier(self.station_id)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class NormalizedRecipe:
    """Standardized internal representation of a recipe across all sources and mods."""

    recipe_id: str
    recipe_type: str
    source_mod: str
    data_source: DataSource
    source_path: str
    outputs: list[RecipeStack] = field(default_factory=list)
    inputs: list[IngredientSlot] = field(default_factory=list)
    machine_info: MachineInfo | None = None
    validation_status: ValidationStatus = ValidationStatus.VALID
    extra_data: dict[str, Any] = field(default_factory=dict)
    raw_data: dict[str, Any] | str | None = None
    warnings: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.recipe_id:
            self.recipe_id = normalize_identifier(self.recipe_id)
        if self.recipe_type:
            self.recipe_type = normalize_identifier(self.recipe_type)
        if not self.source_mod and ":" in self.recipe_id:
            self.source_mod = self.recipe_id.split(":", 1)[0]

    @property
    def primary_output(self) -> RecipeStack | None:
        """Return the primary product of the recipe, if any."""
        for out in self.outputs:
            if out.is_primary:
                return out
        return self.outputs[0] if self.outputs else None

    @property
    def output_item_id(self) -> str | None:
        """Return the resource_id of the primary output."""
        primary = self.primary_output
        return primary.resource_id if primary else None

    @property
    def output_count(self) -> float | int:
        """Return the quantity produced of the primary output."""
        primary = self.primary_output
        return primary.count if primary else 0

    def to_dict(self, include_raw: bool = False) -> dict[str, Any]:
        data: dict[str, Any] = {
            "recipe_id": self.recipe_id,
            "recipe_type": self.recipe_type,
            "source_mod": self.source_mod,
            "data_source": self.data_source.value,
            "source_path": self.source_path,
            "output_item_id": self.output_item_id,
            "output_count": self.output_count,
            "outputs": [out.to_dict() for out in self.outputs],
            "inputs": [inp.to_dict() for inp in self.inputs],
            "machine_info": self.machine_info.to_dict() if self.machine_info else None,
            "validation_status": self.validation_status.value,
            "extra_data": self.extra_data,
            "warnings": self.warnings,
        }
        if include_raw or self.validation_status in (
            ValidationStatus.PARTIAL,
            ValidationStatus.UNSUPPORTED,
            ValidationStatus.INVALID,
        ):
            data["raw_data"] = self.raw_data
        return data


@dataclass
class ImportReport:
    """Comprehensive audit report produced by the recipe import pipeline."""

    instance_name: str
    modpack_version: str
    minecraft_version: str
    mod_loader: str
    total_mods_scanned: int = 0
    total_files_scanned: int = 0
    active_recipes_count: int = 0
    valid_recipes_count: int = 0
    partial_recipes_count: int = 0
    unsupported_recipes_count: int = 0
    invalid_recipes_count: int = 0
    removed_recipes_count: int = 0
    overridden_Duplicates_count: int = 0
    skipped_by_condition_count: int = 0
    replaced_inputs_count: int = 0
    replaced_outputs_count: int = 0
    counts_by_source: dict[str, int] = field(default_factory=dict)
    counts_by_type: dict[str, int] = field(default_factory=dict)
    counts_by_status: dict[str, int] = field(default_factory=dict)
    duplicate_overrides: list[dict[str, str]] = field(default_factory=list)
    errors: list[dict[str, str]] = field(default_factory=list)
    unsupported_types_summary: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

