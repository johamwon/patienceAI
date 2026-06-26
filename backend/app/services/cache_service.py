"""
本地缓存服务

缓存策略：
- 缓存键：查询文本的 MD5 哈希
- 缓存内容：完整的 ExplainResponse JSON
- 过期时间：默认 24 小时（可配置）
- 自动更新：每日定时刷新热门疾病查询
"""

import json
import hashlib
import os
import time
import threading
from datetime import datetime, timedelta
from typing import Optional, Any
from pathlib import Path

CACHE_DIR = Path(__file__).parent.parent / "cache"
CACHE_DB_PATH = CACHE_DIR / "cache_db.json"
CACHE_TTL_HOURS = int(os.getenv("CACHE_TTL_HOURS", "24"))
AUTO_REFRESH_INTERVAL_HOURS = int(os.getenv("AUTO_REFRESH_INTERVAL_HOURS", "24"))

# 热门疾病查询列表（每日自动更新）
HOT_DISEASE_QUERIES = [
    "肺腺癌免疫治疗最新进展",
    "PD-L1表达检测是什么意思",
    "CAR-T疗法实体瘤最新研究",
    "胰腺癌是什么？有哪些亚型",
    "奥希替尼和吉非替尼哪个更好",
    "胶质母细胞瘤电场疗法",
    "SMA基因疗法最新进展",
    "BTK抑制剂耐药后新方案",
]


class CacheService:
    """本地 JSON 文件缓存服务"""

    def __init__(self, cache_dir: Path = CACHE_DIR, ttl_hours: int = CACHE_TTL_HOURS):
        self.cache_dir = cache_dir
        self.ttl_hours = ttl_hours
        self._lock = threading.Lock()
        self._ensure_cache_dir()
        self._load_cache()

    def _ensure_cache_dir(self):
        """确保缓存目录存在"""
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _load_cache(self):
        """从磁盘加载缓存"""
        if CACHE_DB_PATH.exists():
            try:
                with open(CACHE_DB_PATH, "r", encoding="utf-8") as f:
                    self._cache: dict[str, Any] = json.load(f)
            except (json.JSONDecodeError, IOError):
                self._cache = {}
        else:
            self._cache = {}

    def _save_cache(self):
        """保存缓存到磁盘"""
        with open(CACHE_DB_PATH, "w", encoding="utf-8") as f:
            json.dump(self._cache, f, ensure_ascii=False, indent=2)

    def _make_key(self, query: str, max_results: int = 5) -> str:
        """生成缓存键"""
        raw = f"{query}|{max_results}"
        return hashlib.md5(raw.encode("utf-8")).hexdigest()

    def _is_expired(self, entry: dict) -> bool:
        """检查缓存条目是否过期"""
        cached_at = entry.get("cached_at")
        if not cached_at:
            return True
        try:
            cached_time = datetime.fromisoformat(cached_at)
            return datetime.now() - cached_time > timedelta(hours=self.ttl_hours)
        except (ValueError, TypeError):
            return True

    def get(self, query: str, max_results: int = 5) -> Optional[dict]:
        """
        获取缓存结果

        Returns:
            缓存的结果字典，如果未命中或已过期则返回 None
        """
        key = self._make_key(query, max_results)
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None
            if self._is_expired(entry):
                # 过期但后台会自动刷新，先返回旧结果保证响应速度
                return entry.get("data")
            return entry.get("data")

    def set(self, query: str, data: dict, max_results: int = 5):
        """
        写入缓存

        Args:
            query: 原始查询
            data: 要缓存的数据
            max_results: 结果数量
        """
        key = self._make_key(query, max_results)
        with self._lock:
            self._cache[key] = {
                "query": query,
                "data": data,
                "cached_at": datetime.now().isoformat(),
                "expires_at": (datetime.now() + timedelta(hours=self.ttl_hours)).isoformat(),
            }
            self._save_cache()

    def delete(self, query: str, max_results: int = 5):
        """删除缓存条目"""
        key = self._make_key(query, max_results)
        with self._lock:
            self._cache.pop(key, None)
            self._save_cache()

    def clear_expired(self):
        """清除所有过期缓存"""
        with self._lock:
            expired_keys = [
                key for key, entry in self._cache.items()
                if self._is_expired(entry)
            ]
            for key in expired_keys:
                del self._cache[key]
            if expired_keys:
                self._save_cache()
            return len(expired_keys)

    def get_stats(self) -> dict:
        """获取缓存统计信息"""
        with self._lock:
            total = len(self._cache)
            expired = sum(1 for entry in self._cache.values() if self._is_expired(entry))
            valid = total - expired
            return {
                "total": total,
                "valid": valid,
                "expired": expired,
                "ttl_hours": self.ttl_hours,
            }

    def get_all_valid_entries(self) -> list[dict]:
        """获取所有有效缓存条目（用于后台刷新）"""
        with self._lock:
            return [
                entry for entry in self._cache.values()
                if not self._is_expired(entry)
            ]


# ─── 全局单例 ───────────────────────────────────────────────────────────────

cache_service = CacheService()


def start_background_refresh():
    """
    启动后台自动刷新线程

    每天自动刷新热门疾病查询的缓存
    """
    def _refresh_loop():
        while True:
            time.sleep(AUTO_REFRESH_INTERVAL_HOURS * 3600)
            try:
                print("[Cache] 开始自动刷新热门疾病查询缓存...")
                valid_entries = cache_service.get_all_valid_entries()
                refreshed = 0
                for entry in valid_entries:
                    query = entry.get("query", "")
                    # 只刷新热门疾病查询
                    if any(hot_q in query for hot_q in HOT_DISEASE_QUERIES):
                        # 删除旧缓存，下次查询时会自动重新生成
                        cache_service.delete(query)
                        refreshed += 1
                print(f"[Cache] 自动刷新完成，已标记 {refreshed} 条缓存待更新")
            except Exception as e:
                print(f"[Cache] 自动刷新失败: {e}")

    thread = threading.Thread(target=_refresh_loop, daemon=True)
    thread.start()
    print(f"[Cache] 后台自动刷新线程已启动，间隔 {AUTO_REFRESH_INTERVAL_HOURS} 小时")
