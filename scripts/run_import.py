"""CLI script to run the ModpackImporter on Project Infinity 0.1 and save the import report."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from backend.importer.pipeline import ModpackImporter


def main() -> None:
    instance_dir = Path(r"C:\Users\olx\curseforge\minecraft\Instances\Project Infinity 0.1")
    output_dir = ROOT_DIR / "data"
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"[*] Starting import of: {instance_dir}")
    t0 = time.perf_counter()
    importer = ModpackImporter(instance_dir)
    result = importer.run(load_tags=True)
    elapsed = time.perf_counter() - t0

    report = result.report
    assert report is not None

    print(f"[+] Import finished in {elapsed:.2f}s")
    print(f"    Instance: {report.instance_name} ({report.modpack_version})")
    print(f"    Minecraft: {report.minecraft_version} | Loader: {report.mod_loader}")
    print(f"    Mods scanned: {report.total_mods_scanned}")
    print(f"    Total recipe files scanned: {report.total_files_scanned}")
    print(f"    Skipped by Forge/Bookshelf conditions: {report.skipped_by_condition_count}")
    print(f"    Duplicate/Datapack overrides: {report.overridden_Duplicates_count}")
    print(f"    Removed recipes (Datapack {{}} + KubeJS remove_recipes.js): {report.removed_recipes_count}")
    print(f"    Replaced inputs count: {report.replaced_inputs_count} | Replaced outputs count: {report.replaced_outputs_count}")
    print(f"    Active recipes total: {report.active_recipes_count}")
    print(f"      - VALID (fully interpreted): {report.valid_recipes_count}")
    print(f"      - PARTIAL: {report.partial_recipes_count}")
    print(f"      - UNSUPPORTED (dynamic/special preserved): {report.unsupported_recipes_count}")
    print(f"      - INVALID: {report.invalid_recipes_count}")

    print("\n[*] Top 15 Unsupported/Partial Recipe Types:")
    for rtype, cnt in sorted(report.unsupported_types_summary.items(), key=lambda x: x[1], reverse=True)[:15]:
        print(f"    {rtype}: {cnt}")

    report_path = output_dir / "import_report.json"
    report_path.write_text(
        json.dumps(report.to_dict(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"\n[+] Saved detailed report to: {report_path}")


if __name__ == "__main__":
    main()

