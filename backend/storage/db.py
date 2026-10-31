"""SQLite persistence layer for caching imported modpack recipes and crafting targets."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from backend.engine.models import CraftingTreeResult, DependencyNode
from backend.models.recipe import NormalizedRecipe
from backend.storage.item_names import item_names


class DatabaseStorage:
    """Manages SQLite storage for recipes, crafting targets, and imported modpack data."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS recipes (
                    recipe_id TEXT PRIMARY KEY,
                    output_item_id TEXT,
                    output_count REAL,
                    recipe_type TEXT,
                    source_mod TEXT,
                    data_source TEXT,
                    validation_status TEXT,
                    recipe_json TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_recipes_output ON recipes(output_item_id);
                CREATE INDEX IF NOT EXISTS idx_recipes_type ON recipes(recipe_type);

                CREATE TABLE IF NOT EXISTS crafting_goals (
                    goal_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    target_item_key TEXT NOT NULL,
                    target_count REAL NOT NULL,
                    status TEXT DEFAULT 'in_progress',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_steps TEXT DEFAULT '[]',
                    available_materials TEXT DEFAULT '{}',
                    tree_data TEXT
                );

                CREATE TABLE IF NOT EXISTS recent_items (
                    item_key TEXT PRIMARY KEY,
                    last_viewed TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            try:
                conn.execute("ALTER TABLE recipes ADD COLUMN display_name TEXT;")
            except sqlite3.OperationalError:
                pass
            conn.execute("CREATE INDEX IF NOT EXISTS idx_recipes_display ON recipes(display_name);")
            conn.commit()

    def save_recipes(self, recipes: list[NormalizedRecipe]) -> None:
        """Batch insert or replace recipes into SQLite."""
        with self._get_connection() as conn:
            conn.executemany(
                """
                INSERT OR REPLACE INTO recipes (
                    recipe_id, output_item_id, display_name, output_count, recipe_type,
                    source_mod, data_source, validation_status, recipe_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        r.recipe_id,
                        r.output_item_id,
                        item_names.get_display_name(r.output_item_id),
                        r.output_count,
                        r.recipe_type,
                        r.source_mod,
                        r.data_source.value,
                        r.validation_status.value,
                        json.dumps(r.to_dict(include_raw=True), ensure_ascii=False),
                    )
                    for r in recipes
                ],
            )
            conn.commit()

    def search_items(self, query: str, limit: int = 50) -> list[dict[str, Any]]:
        """Search items by either technical ID (mod:item) or formatted display name (Minecraft name)."""
        clean_q = query.strip()
        if not clean_q:
            return []

        clean_like = f"%{clean_q}%"
        clean_lower = clean_q.lower()

        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT DISTINCT output_item_id as item_id, display_name, source_mod, count(*) as recipes_count
                FROM recipes
                WHERE validation_status != 'removed'
                  AND (
                    output_item_id LIKE ?
                    OR display_name LIKE ?
                  )
                GROUP BY output_item_id
                ORDER BY
                  CASE
                    WHEN LOWER(output_item_id) = ? OR LOWER(display_name) = ? THEN 1
                    WHEN LOWER(output_item_id) LIKE ? OR LOWER(display_name) LIKE ? THEN 2
                    ELSE 3
                  END,
                  recipes_count DESC,
                  display_name ASC
                LIMIT ?
                """,
                (
                    clean_like,
                    clean_like,
                    clean_lower,
                    clean_lower,
                    f"{clean_lower}%",
                    f"{clean_lower}%",
                    limit,
                ),
            ).fetchall()

            results = []
            for r in rows:
                d = dict(r)
                d["display_name"] = d.get("display_name") or item_names.get_display_name(d["item_id"])
                d["mod_name"] = item_names.format_mod_name(d.get("source_mod"))
                results.append(d)
            return results

    def record_recent_item(self, item_key: str) -> None:
        """Record an item as recently viewed."""
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO recent_items (item_key, last_viewed)
                VALUES (?, CURRENT_TIMESTAMP)
                """,
                (item_key,),
            )
            conn.commit()

    def get_recent_items(self, limit: int = 15) -> list[str]:
        """Get the most recently inspected items."""
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT item_key FROM recent_items
                ORDER BY last_viewed DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [r["item_key"] for r in rows]

    def save_goal(
        self,
        goal_id: str,
        title: str,
        target_item_key: str,
        target_count: float | int,
        tree_result: CraftingTreeResult | None = None,
    ) -> None:
        """Save or update a crafting objective."""
        tree_json = json.dumps(tree_result.to_dict(), ensure_ascii=False) if tree_result else None
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO crafting_goals (
                    goal_id, title, target_item_key, target_count, updated_at, tree_data
                ) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, ?)
                """,
                (goal_id, title, target_item_key, target_count, tree_json),
            )
            conn.commit()

    def get_goals(self) -> list[dict[str, Any]]:
        """Fetch all saved crafting goals."""
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT goal_id, title, target_item_key, target_count, status,
                       created_at, updated_at, completed_steps, available_materials
                FROM crafting_goals
                ORDER BY updated_at DESC
                """
            ).fetchall()
            goals = []
            for r in rows:
                g = dict(r)
                g["completed_steps"] = json.loads(g["completed_steps"])
                g["available_materials"] = json.loads(g["available_materials"])
                goals.append(g)
            return goals

    def toggle_goal_step(self, goal_id: str, step_id: str) -> list[str]:
        """Toggle a crafting step as completed/uncompleted in a goal."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT completed_steps FROM crafting_goals WHERE goal_id = ?",
                (goal_id,),
            ).fetchone()
            if not row:
                return []
            steps = set(json.loads(row["completed_steps"]))
            if step_id in steps:
                steps.remove(step_id)
            else:
                steps.add(step_id)
            step_list = sorted(steps)
            conn.execute(
                """
                UPDATE crafting_goals
                SET completed_steps = ?, updated_at = CURRENT_TIMESTAMP
                WHERE goal_id = ?
                """,
                (json.dumps(step_list), goal_id),
            )
            conn.commit()
            return step_list

