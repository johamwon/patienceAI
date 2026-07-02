from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic_settings import BaseSettings
from dotenv import load_dotenv
import os

load_dotenv()

# ─── Settings ───────────────────────────────────────────────────────────────

class Settings(BaseSettings):
    knows_base_url: str = "https://api.nullht.com/v1"
    knows_api_key: str = ""
    llm_api_key: str = ""
    llm_base_url: str = "https://api.siliconflow.cn/v1"
    llm_model: str = "Qwen/Qwen2.5-7B-Instruct"
    app_env: str = "development"

    class Config:
        env_file = ".env"

settings = Settings()
FRONTEND_DIST_DIR = Path(os.getenv("FRONTEND_DIST_DIR", "")).resolve() if os.getenv("FRONTEND_DIST_DIR") else None


def _frontend_index_path() -> Path | None:
    if not FRONTEND_DIST_DIR:
        return None
    index = FRONTEND_DIST_DIR / "index.html"
    return index if index.exists() else None

# ─── App ────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="医语桥 API",
    description="面向患者的循证医学检索与通俗化解释 Agent",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Health ─────────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    index = _frontend_index_path()
    if index:
        return FileResponse(index)
    return {
        "name": "医语桥 API",
        "version": "0.1.0",
        "docs": "/docs",
        "health": "/health",
    }

@app.get("/health")
async def health():
    return {"status": "ok", "env": settings.app_env}

# ─── API Routes ─────────────────────────────────────────────────────────────

from .api import search, explain, evaluate, visit_prep
from .services.cache_service import cache_service

app.include_router(search.router, prefix="/api/v1", tags=["search"])
app.include_router(explain.router, prefix="/api/v1", tags=["explain"])
app.include_router(evaluate.router, prefix="/api/v1", tags=["evaluate"])
app.include_router(visit_prep.router, prefix="/api/v1", tags=["visit-prep"])

if FRONTEND_DIST_DIR and FRONTEND_DIST_DIR.exists():
    assets_dir = FRONTEND_DIST_DIR / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="frontend-assets")

# ─── Cache Management ────────────────────────────────────────────────────────

@app.get("/api/v1/cache/stats")
async def cache_stats():
    """获取缓存统计信息"""
    return cache_service.get_stats()


@app.post("/api/v1/cache/clear-expired")
async def cache_clear_expired():
    """清除过期缓存"""
    cleared = cache_service.clear_expired()
    return {"cleared": cleared, "message": f"已清除 {cleared} 条过期缓存"}


@app.delete("/api/v1/cache/{query:path}")
async def cache_delete(query: str):
    """删除指定查询的缓存"""
    cache_service.delete(query)
    return {"message": f"已删除缓存: {query}"}


@app.get("/{full_path:path}", include_in_schema=False)
async def frontend_spa(full_path: str):
    """ModelScope Docker 部署时托管前端单页应用。"""
    index = _frontend_index_path()
    if not index:
        raise HTTPException(status_code=404, detail="Not Found")
    candidate = (FRONTEND_DIST_DIR / full_path).resolve()
    if (
        FRONTEND_DIST_DIR
        and str(candidate).startswith(str(FRONTEND_DIST_DIR))
        and candidate.exists()
        and candidate.is_file()
    ):
        return FileResponse(candidate)
    return FileResponse(index)
