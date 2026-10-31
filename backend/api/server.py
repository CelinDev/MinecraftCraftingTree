"""FastAPI REST server exposing modpack search, crafting trees, recipes, and goals."""

from __future__ import annotations

import json
import pickle
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.engine.crafting import DependencyEngine
from backend.importer.discovery import discover_instance
from backend.importer.pipeline import ModpackImporter
from backend.storage.db import DatabaseStorage
from backend.storage.fast_icons import FastStaticIconService, STATIC_ICONS_DIR

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = ROOT_DIR / "data"
FRONTEND_DIST = ROOT_DIR / "frontend" / "dist"
DB_PATH = DATA_DIR / "crafting_explorer.db"
CACHE_PATH = DATA_DIR / "modpack_cache.pkl"
INSTANCE_PATH = Path(r"C:\Users\olx\curseforge\minecraft\Instances\Project Infinity 0.1")

# Global in-memory engine, storage, and fast icon service
storage = DatabaseStorage(DB_PATH)
fast_icons = FastStaticIconService(STATIC_ICONS_DIR)
_engine: DependencyEngine | None = None
_importer_info: dict[str, Any] = {}


def get_engine() -> DependencyEngine:
    global _engine, _importer_info
    if _engine is None:
        # 1. Fast path: load pre-indexed binary cache if available
        if CACHE_PATH.exists():
            try:
                with open(CACHE_PATH, "rb") as f:
                    recipes, tag_registry, report = pickle.load(f)
                _engine = DependencyEngine(recipes, tag_registry=tag_registry)
                if report:
                    _importer_info = report.to_dict()
                return _engine
            except Exception:
                pass

        # 2. Slow path: scan instance directly and write cache
        importer = ModpackImporter(INSTANCE_PATH)
        res = importer.run(load_tags=True)
        _engine = DependencyEngine(res.recipes, tag_registry=res.tag_registry)
        storage.save_recipes(list(res.recipes.values()))
        if res.report:
            _importer_info = res.report.to_dict()

        try:
            with open(CACHE_PATH, "wb") as f:
                pickle.dump(
                    (res.recipes, res.tag_registry, res.report),
                    f,
                    protocol=pickle.HIGHEST_PROTOCOL,
                )
        except Exception:
            pass

    return _engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Warm up engine and database on server startup
    get_engine()
    yield


app = FastAPI(
    title="Minecraft Crafting Explorer API",
    description="REST API for recipe discovery, dependency trees, and production planning.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class CraftingTreeRequest(BaseModel):
    item_key: str
    count: float | int = 1
    selected_recipes: dict[str, str] = {}
    prune_basic_resources: bool = True
    avoid_mystical_agriculture: bool = True


class CraftingGoalRequest(BaseModel):
    goal_id: str
    title: str
    target_item_key: str
    target_count: float | int


@app.get("/api/status")
def get_status() -> dict[str, Any]:
    """Get system and modpack import status."""
    engine = get_engine()
    return {
        "status": "ready",
        "active_recipes_count": len(engine.recipes),
        "modpack_info": _importer_info,
    }


@app.get("/api/search")
def search_items(q: str = Query(..., min_length=1), limit: int = 40) -> list[dict[str, Any]]:
    """Search all known items by query string."""
    return storage.search_items(q, limit=limit)


@app.get("/api/recent")
def get_recent_items() -> list[str]:
    """Get list of recently viewed item keys."""
    return storage.get_recent_items()


@app.get("/api/items/{item_key:path}/icon")
def get_item_icon(item_key: str):
    """Serve the PNG texture icon directly from pre-extracted disk files with HTTP caching."""
    icon_path = fast_icons.get_icon_path(item_key)
    if icon_path and icon_path.exists():
        return FileResponse(
            icon_path,
            media_type="image/png",
            headers={"Cache-Control": "public, max-age=86400, immutable"},
        )
    # Transparent 1x1 PNG fallback with caching
    transparent_png_1x1 = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06"
        b"\x00\x00\x00\x1f\x15c4\x00\x00\x00\rIDATx\x9cc`\x00\x00\x00\x02\x00\x01H\xaf"
        b"\xa4q\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    return Response(
        content=transparent_png_1x1,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400, immutable"},
    )


@app.get("/api/items/{item_key:path}/recipes")
def get_item_recipes(item_key: str) -> list[dict[str, Any]]:
    """Get all recipes that produce the given item or tag."""
    engine = get_engine()
    storage.record_recent_item(item_key)
    recs = engine.find_recipes_for_item(item_key)
    return [r.to_dict(include_raw=True) for r in recs]


@app.post("/api/crafting-tree")
def calculate_crafting_tree(req: CraftingTreeRequest) -> dict[str, Any]:
    """Calculate recursive dependency tree, steps, and consolidated materials."""
    engine = get_engine()
    storage.record_recent_item(req.item_key)
    tree_result = engine.build_crafting_tree(
        target_item=req.item_key,
        target_count=req.count,
        selected_recipes=req.selected_recipes,
        prune_basic=req.prune_basic_resources,
        avoid_mystical_agriculture=req.avoid_mystical_agriculture,
    )
    return tree_result.to_dict()


@app.get("/api/goals")
def get_crafting_goals() -> list[dict[str, Any]]:
    """Get all saved crafting goals."""
    return storage.get_goals()


@app.post("/api/goals")
def create_crafting_goal(req: CraftingGoalRequest) -> dict[str, Any]:
    """Create or update a crafting objective."""
    engine = get_engine()
    tree = engine.build_crafting_tree(req.target_item_key, req.target_count)
    storage.save_goal(req.goal_id, req.title, req.target_item_key, req.target_count, tree)
    return {"status": "saved", "goal_id": req.goal_id}


@app.post("/api/goals/{goal_id}/toggle-step/{step_id}")
def toggle_goal_step(goal_id: str, step_id: str) -> dict[str, Any]:
    """Toggle a step as completed in a crafting goal."""
    completed = storage.toggle_goal_step(goal_id, step_id)
    return {"goal_id": goal_id, "completed_steps": completed}


# Mount built frontend dist for full single-port experience
if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.api.server:app", host="127.0.0.1", port=8000, reload=False)

