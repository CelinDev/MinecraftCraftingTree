"""Main recipe import pipeline orchestrating JARs, configs, datapacks, and KubeJS layers."""

from __future__ import annotations

import json
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from backend.importer.adapters import parse_recipe_json
from backend.importer.discovery import ModpackInstanceInfo, discover_instance
from backend.importer.kubejs_processor import (
    RemovalFilter,
    ReplacementRule,
    parse_hnn_data_models,
    parse_kubejs_server_scripts,
    parse_singularities_from_config,
)
from backend.importer.tags import (
    TagRegistry,
    apply_kubejs_tag_scripts,
    load_tags_from_datapack_dir,
    load_tags_from_jar,
)
from backend.models.recipe import (
    DataSource,
    ImportReport,
    NormalizedRecipe,
    ResourceType,
    ValidationStatus,
    normalize_identifier,
)

_RECIPE_ENTRY_RE = re.compile(r"^data/([^/]+)/recipes/(.+)\.json$")


@dataclass
class ImportResult:
    """Contains the active normalized recipes, audit history, tag registry, and summary report."""

    instance_info: ModpackInstanceInfo
    recipes: dict[str, NormalizedRecipe] = field(default_factory=dict)
    removed_recipes: dict[str, NormalizedRecipe] = field(default_factory=dict)
    tag_registry: TagRegistry = field(default_factory=TagRegistry)
    report: ImportReport | None = None

    def get_recipes_for_output(self, item_id: str) -> list[NormalizedRecipe]:
        """Return all active recipes that produce the specified item_id."""
        norm_target = normalize_identifier(item_id.lstrip("#"))
        matches: list[NormalizedRecipe] = []
        for rec in self.recipes.values():
            if rec.validation_status in (ValidationStatus.REMOVED, ValidationStatus.INVALID):
                continue
            if any(out.resource_id == norm_target for out in rec.outputs):
                matches.append(rec)
        return matches


class ModpackImporter:
    """Layered importer that reconstructs the active recipes of a Minecraft modpack."""

    def __init__(
        self,
        instance_dir: str | Path,
        curseforge_install_dir: str | Path | None = None,
    ) -> None:
        self.instance_info = discover_instance(instance_dir, curseforge_install_dir)
        self.tag_registry = TagRegistry()
        self.report = ImportReport(
            instance_name=self.instance_info.name,
            modpack_version=self.instance_info.modpack_version,
            minecraft_version=self.instance_info.minecraft_version,
            mod_loader=self.instance_info.mod_loader,
            total_mods_scanned=len(self.instance_info.mod_jars),
        )
        self._active_recipes: dict[str, NormalizedRecipe] = {}
        self._removed_recipes: dict[str, NormalizedRecipe] = {}

    def run(self, load_tags: bool = True) -> ImportResult:
        """Execute the full multi-layer import pipeline."""
        # Layer 1: Tags & Almost Unified Configuration
        if self.instance_info.config_dir:
            au_path = self.instance_info.config_dir / "almostunified" / "unify.json"
            self.tag_registry.load_almost_unified_config(au_path)

        if load_tags:
            if self.instance_info.vanilla_jar:
                load_tags_from_jar(self.instance_info.vanilla_jar, self.tag_registry)
            for jar_path in self.instance_info.mod_jars:
                load_tags_from_jar(jar_path, self.tag_registry)
            if self.instance_info.kubejs_dir:
                load_tags_from_datapack_dir(self.instance_info.kubejs_dir / "data", self.tag_registry)
                apply_kubejs_tag_scripts(self.instance_info.kubejs_dir / "server_scripts", self.tag_registry)

        # Layer 2a: Vanilla 1.20.1 JAR Recipes
        if self.instance_info.vanilla_jar:
            self._ingest_jar(self.instance_info.vanilla_jar, DataSource.VANILLA_JAR)

        # Layer 2b: All Mod JAR Recipes
        for jar_path in self.instance_info.mod_jars:
            self._ingest_jar(jar_path, DataSource.MOD_JAR)

        # Layer 2c: Config-Generated Recipes (Extended Crafting Singularities & HNN Data Models)
        if self.instance_info.config_dir:
            for sing_rec in parse_singularities_from_config(self.instance_info.config_dir):
                self._register_recipe(sing_rec)
        if self.instance_info.kubejs_dir:
            for hnn_rec in parse_hnn_data_models(self.instance_info.kubejs_dir / "data"):
                self._register_recipe(hnn_rec)

        # Layer 3: KubeJS Datapack Overrides (`kubejs/data/*/recipes/*.json`)
        if self.instance_info.kubejs_dir:
            self._ingest_datapack_dir(
                self.instance_info.kubejs_dir / "data",
                DataSource.KUBEJS_DATAPACK,
            )

        # Layer 4: KubeJS Server Scripts (Removals -> Additions -> Replacements)
        if self.instance_info.kubejs_dir:
            scripts_dir = self.instance_info.kubejs_dir / "server_scripts"
            kjs_analysis = parse_kubejs_server_scripts(
                scripts_dir,
                loaded_mods=self.instance_info.loaded_mod_ids,
                tag_registry=self.tag_registry,
            )
            self._apply_removals(kjs_analysis.removal_filters)
            for added_rec in kjs_analysis.added_recipes:
                self._register_recipe(added_rec)
            self._apply_replacements(kjs_analysis.replacement_rules)

        self._finalize_report()
        return ImportResult(
            instance_info=self.instance_info,
            recipes=self._active_recipes,
            removed_recipes=self._removed_recipes,
            tag_registry=self.tag_registry,
            report=self.report,
        )

    def _register_recipe(self, recipe: NormalizedRecipe) -> None:
        """Register or override a recipe by its unique recipe_id, recording duplicate overrides."""
        rec_id = recipe.recipe_id
        if recipe.validation_status == ValidationStatus.REMOVED:
            if rec_id in self._active_recipes:
                old = self._active_recipes.pop(rec_id)
                old.validation_status = ValidationStatus.REMOVED
                old.warnings.append(f"Removed via empty datapack override from {recipe.source_path}")
                self._removed_recipes[rec_id] = old
            else:
                self._removed_recipes[rec_id] = recipe
            return

        if rec_id in self._active_recipes:
            prev = self._active_recipes[rec_id]
            self.report.overridden_Duplicates_count += 1
            if len(self.report.duplicate_overrides) < 200:
                self.report.duplicate_overrides.append(
                    {
                        "recipe_id": rec_id,
                        "previous_source": f"{prev.data_source.value}:{prev.source_path}",
                        "new_source": f"{recipe.data_source.value}:{recipe.source_path}",
                    }
                )

        self._active_recipes[rec_id] = recipe

    def _ingest_jar(self, jar_path: Path, data_source: DataSource) -> None:
        """Scan a single JAR archive for `data/<namespace>/recipes/<path>.json` entries."""
        if not jar_path.exists():
            return
        try:
            with zipfile.ZipFile(jar_path, "r") as zf:
                for entry_name in zf.namelist():
                    if entry_name.endswith("/"):
                        continue
                    m = _RECIPE_ENTRY_RE.match(entry_name)
                    if not m:
                        continue
                    namespace, rel_path = m.groups()
                    recipe_id = f"{namespace}:{rel_path}"
                    source_ref = f"{jar_path.name}!/{entry_name}"
                    self.report.total_files_scanned += 1
                    try:
                        raw_bytes = zf.read(entry_name)
                        raw_text = raw_bytes.decode("utf-8", errors="replace").strip()
                        data = json.loads(raw_text) if raw_text else {}
                    except Exception as exc:
                        self.report.errors.append({"source": source_ref, "error": str(exc)})
                        inv_rec = NormalizedRecipe(
                            recipe_id=recipe_id,
                            recipe_type="unknown:invalid_json",
                            source_mod=namespace,
                            data_source=data_source,
                            source_path=source_ref,
                            validation_status=ValidationStatus.INVALID,
                            raw_data=raw_text if "raw_text" in locals() else None,
                            warnings=[f"Invalid JSON: {exc}"],
                        )
                        self._register_recipe(inv_rec)
                        continue

                    parsed, skipped = parse_recipe_json(
                        recipe_id=recipe_id,
                        data=data,
                        data_source=data_source,
                        source_path=source_ref,
                        loaded_mods=self.instance_info.loaded_mod_ids,
                        tag_registry=self.tag_registry,
                    )
                    if skipped:
                        self.report.skipped_by_condition_count += 1
                        continue
                    if parsed:
                        self._register_recipe(parsed)
        except Exception as exc:
            self.report.errors.append({"source": jar_path.name, "error": f"Archive error: {exc}"})

    def _ingest_datapack_dir(self, data_dir: Path, data_source: DataSource) -> None:
        """Scan an unpacked datapack directory (`data/<namespace>/recipes/**/*.json`)."""
        if not data_dir.exists():
            return
        for namespace_dir in sorted(data_dir.iterdir()):
            if not namespace_dir.is_dir():
                continue
            namespace = namespace_dir.name
            recipes_root = namespace_dir / "recipes"
            if not recipes_root.exists():
                continue
            for json_file in sorted(recipes_root.rglob("*.json")):
                rel_path = json_file.relative_to(recipes_root).with_suffix("").as_posix()
                recipe_id = f"{namespace}:{rel_path}"
                source_ref = json_file.relative_to(data_dir.parent).as_posix()
                self.report.total_files_scanned += 1
                try:
                    raw_text = json_file.read_text(encoding="utf-8", errors="replace").strip()
                    data = json.loads(raw_text) if raw_text else {}
                except Exception as exc:
                    self.report.errors.append({"source": source_ref, "error": str(exc)})
                    inv_rec = NormalizedRecipe(
                        recipe_id=recipe_id,
                        recipe_type="unknown:invalid_json",
                        source_mod=namespace,
                        data_source=data_source,
                        source_path=source_ref,
                        validation_status=ValidationStatus.INVALID,
                        raw_data=raw_text if "raw_text" in locals() else None,
                        warnings=[f"Invalid JSON: {exc}"],
                    )
                    self._register_recipe(inv_rec)
                    continue

                parsed, skipped = parse_recipe_json(
                    recipe_id=recipe_id,
                    data=data,
                    data_source=data_source,
                    source_path=source_ref,
                    loaded_mods=self.instance_info.loaded_mod_ids,
                    tag_registry=self.tag_registry,
                )
                if skipped:
                    self.report.skipped_by_condition_count += 1
                    continue
                if parsed:
                    self._register_recipe(parsed)

    def _apply_removals(self, filters: list[RemovalFilter]) -> None:
        """Apply KubeJS recipe removal rules against all currently active recipes."""
        if not filters:
            return

        # Fast index for exact ID removals
        exact_ids: set[str] = set()
        general_filters: list[RemovalFilter] = []
        for f in filters:
            if (
                f.recipe_id
                and not f.output
                and not f.output_regex
                and not f.input_item
                and not f.recipe_type
                and not f.mod
            ):
                exact_ids.add(normalize_identifier(f.recipe_id))
            else:
                general_filters.append(f)

        for rid in exact_ids:
            if rid in self._active_recipes:
                rec = self._active_recipes.pop(rid)
                rec.validation_status = ValidationStatus.REMOVED
                rec.warnings.append("Removed by KubeJS ID filter")
                self._removed_recipes[rid] = rec

        to_remove: list[str] = []
        for rid, rec in self._active_recipes.items():
            if any(gf.matches(rec) for gf in general_filters):
                to_remove.append(rid)

        for rid in to_remove:
            rec = self._active_recipes.pop(rid)
            rec.validation_status = ValidationStatus.REMOVED
            rec.warnings.append("Removed by KubeJS filter")
            self._removed_recipes[rid] = rec

    def _apply_replacements(self, rules: list[ReplacementRule]) -> None:
        """Apply KubeJS replaceInput and replaceOutput rules across active recipes."""
        if not rules:
            return

        for rule in rules:
            target_is_tag = rule.target_item.startswith("#")
            norm_target = normalize_identifier(rule.target_item.lstrip("#"))
            replacement_is_tag = rule.replacement_item.startswith("#")
            norm_replacement = normalize_identifier(rule.replacement_item.lstrip("#"))
            new_r_type = ResourceType.TAG if replacement_is_tag else ResourceType.ITEM

            for rec in self._active_recipes.values():
                if not self._filter_or_all_matches(rule.filter_criteria, rec):
                    continue

                if rule.is_output:
                    modified_out = False
                    for out in rec.outputs:
                        if out.resource_id == norm_target:
                            out.resource_id = norm_replacement
                            out.resource_type = new_r_type
                            modified_out = True
                    if modified_out:
                        self.report.replaced_outputs_count += 1
                else:
                    modified_in = False
                    for slot in rec.inputs:
                        for alt in slot.alternatives:
                            if target_is_tag and alt.resource_type == ResourceType.TAG and alt.resource_id == norm_target:
                                alt.resource_id = norm_replacement
                                alt.resource_type = new_r_type
                                modified_in = True
                            elif not target_is_tag and alt.resource_type == ResourceType.ITEM and alt.resource_id == norm_target:
                                alt.resource_id = norm_replacement
                                alt.resource_type = new_r_type
                                modified_in = True
                    if modified_in:
                        self.report.replaced_inputs_count += 1

    @staticmethod
    def _filter_or_all_matches(f: RemovalFilter, rec: NormalizedRecipe) -> bool:
        """Like RemovalFilter.matches, except an empty filter {} matches ALL recipes."""
        if not any(
            x is not None
            for x in (f.recipe_id, f.output, f.output_regex, f.input_item, f.recipe_type, f.mod)
        ):
            return True
        return f.matches(rec)

    def _finalize_report(self) -> None:
        """Compute summary statistics for the import report."""
        self.report.active_recipes_count = len(self.active_recipes)
        self.report.removed_recipes_count = len(self._removed_recipes)

        for rec in self._active_recipes.values():
            src_key = rec.data_source.value
            self.report.counts_by_source[src_key] = self.report.counts_by_source.get(src_key, 0) + 1

            st_key = rec.validation_status.value
            self.report.counts_by_status[st_key] = self.report.counts_by_status.get(st_key, 0) + 1

            self.report.counts_by_type[rec.recipe_type] = (
                self.report.counts_by_type.get(rec.recipe_type, 0) + 1
            )

            if rec.validation_status == ValidationStatus.VALID:
                self.report.valid_recipes_count += 1
            elif rec.validation_status == ValidationStatus.PARTIAL:
                self.report.partial_recipes_count += 1
            elif rec.validation_status == ValidationStatus.UNSUPPORTED:
                self.report.unsupported_recipes_count += 1
                self.report.unsupported_types_summary[rec.recipe_type] = (
                    self.report.unsupported_types_summary.get(rec.recipe_type, 0) + 1
                )
            elif rec.validation_status == ValidationStatus.INVALID:
                self.report.invalid_recipes_count += 1

        self.report.counts_by_status[ValidationStatus.REMOVED.value] = len(self._removed_recipes)

    @property
    def active_recipes(self) -> dict[str, NormalizedRecipe]:
        return self._active_recipes

