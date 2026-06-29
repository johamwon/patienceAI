from fastapi import FastAPI, HTTPException
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

# ─── App ────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="患癌知光 API",
    description="面向患者的疑难杂症科研动态检索与通俗化解释 Agent",
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
    return {
        "name": "患癌知光 API",
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
