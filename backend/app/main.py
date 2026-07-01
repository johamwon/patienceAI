from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
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

@app.get("/health")
async def health():
    return {"status": "ok", "env": settings.app_env}

# ─── API Routes ─────────────────────────────────────────────────────────────

from .api import search, explain, evaluate, visit_prep, radar
from .services.cache_service import cache_service
from .services.radar.patrol import start_daily_patrol

app.include_router(search.router, prefix="/api/v1", tags=["search"])
app.include_router(explain.router, prefix="/api/v1", tags=["explain"])
app.include_router(evaluate.router, prefix="/api/v1", tags=["evaluate"])
app.include_router(visit_prep.router, prefix="/api/v1", tags=["visit-prep"])
app.include_router(radar.router, prefix="/api/v1", tags=["radar"])

start_daily_patrol()

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


# ─── 前端静态托管（单容器部署：FastAPI 同时托管前端 dist）─────────────────────
# 使用 pathlib 可靠地解析路径，支持多种部署场景
from pathlib import Path
import sys

_POSSIBLE_FRONTEND_DIST = [
    # 容器部署：WORKDIR=/app, 文件结构 /app/backend/app/main.py, /app/frontend/dist
    Path(__file__).resolve().parent.parent.parent / "frontend" / "dist",
    # 本地开发：从 backend/app/main.py 向上 3 级到项目根
    Path(__file__).resolve().parent.parent.parent.parent / "frontend" / "dist",
]

_FRONTEND_DIST = None
for _candidate in _POSSIBLE_FRONTEND_DIST:
    if _candidate.is_dir() and (_candidate / "index.html").exists():
        _FRONTEND_DIST = _candidate
        break

print(f"[startup] __file__ = {__file__}", file=sys.stderr)
print(f"[startup] FRONTEND_DIST = {_FRONTEND_DIST}", file=sys.stderr)
if _FRONTEND_DIST:
    print(f"[startup] Frontend dist contents: {list(_FRONTEND_DIST.iterdir())}", file=sys.stderr)

if _FRONTEND_DIST:
    # 托管 /assets 等静态资源
    app.mount("/assets", StaticFiles(directory=str(_FRONTEND_DIST / "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str):
        """SPA 兜底：非 API 路由一律返回 index.html，交给前端路由处理"""
        candidate = _FRONTEND_DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(str(candidate))
        return FileResponse(str(_FRONTEND_DIST / "index.html"))
