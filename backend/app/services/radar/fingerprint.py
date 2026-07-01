"""
新进展判定与去重纯逻辑（R5.1, R5.2, R5.6）

对一条证据（evidence dict）计算稳定去重键 Progress_Fingerprint，并判定其
是否为"值得推送的新进展"（质量达标且新鲜）。所有函数均为纯函数、对缺失
字段安全处理、不抛异常，便于属性/单元测试（3.2）与巡检编排（6.x）复用。

参考 research_stage.py 与 search.py 的稳健字段/日期处理风格。
"""

import hashlib
import os
import re
from datetime import date, datetime
from typing import Optional

# ---------------------------------------------------------------------------
# 阈值参数（模块级，环境变量可配）
# ---------------------------------------------------------------------------

# 质量达标：证据等级属于以下集合
RADAR_MIN_LEVELS = {"high", "moderate"}

# 质量达标：来源类型属于以下集合（新指南 / 新临床试验 / 会议进展）
RADAR_FRESH_SOURCES = {"guide", "trial", "meeting"}

# 新鲜度窗口（天），默认 30 天，可经环境变量 RADAR_FRESH_DAYS 覆盖
try:
    RADAR_FRESH_DAYS = int(os.getenv("RADAR_FRESH_DAYS", "30"))
except (TypeError, ValueError):
    RADAR_FRESH_DAYS = 30


def _clean_str(value) -> str:
    """把任意值安全转为去空白的字符串；非字符串或缺失返回空串。"""
    if isinstance(value, str):
        return value.strip()
    return ""


def progress_fingerprint(evidence: dict) -> str:
    """
    计算稳定去重键（R5.2）。

    优先级：nct_id > doi > pmid。任一存在且非空则直接返回带前缀的它，
    形如 "nct:NCT01234567" / "doi:10.x/y" / "pmid:12345678"。
    三者都缺失时，回退为
        sha1(f"{title}|{source_type}|{publish_date}").hexdigest()

    对同一 evidence 幂等（相同输入恒返回相同键）。对缺失字段、非字符串
    字段安全处理，不抛异常。
    """
    safe = evidence if isinstance(evidence, dict) else {}

    nct_id = _clean_str(safe.get("nct_id"))
    if nct_id:
        return f"nct:{nct_id}"

    doi = _clean_str(safe.get("doi"))
    if doi:
        return f"doi:{doi}"

    pmid = _clean_str(safe.get("pmid"))
    if pmid:
        return f"pmid:{pmid}"

    # 回退：标题 + 来源类型 + 发表时间 的 sha1 指纹
    title = _clean_str(safe.get("title"))
    source_type = _clean_str(safe.get("source_type"))
    publish_date = _normalize_publish_date_str(safe.get("publish_date"))

    raw = f"{title}|{source_type}|{publish_date}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _normalize_publish_date_str(value) -> str:
    """
    把 publish_date 归一化为稳定字符串，用于指纹计算。

    - date / datetime 对象 → ISO 格式（取 date 部分）
    - 字符串 → 去空白后的原样字符串
    - None / 其他 → 空串

    仅用于指纹稳定性，不做有效性校验。
    """
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str):
        return value.strip()
    return str(value)


def _parse_publish_date(value) -> Optional[date]:
    """
    把 publish_date 解析为 date 对象，兼容多种输入（参考 search.py 风格）。

    支持：
    - datetime / date 对象
    - ISO 字符串 "2024-01-15"、分隔符容忍 "2024/01/15"、"2024.01"
    - 仅年份字符串 "2024"（视为该年 1 月 1 日）

    无法解析或缺失 → None。不抛异常。
    """
    if value is None:
        return None

    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value

    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        parts = re.split(r"[-/.]", text)
        try:
            year = int(parts[0])
        except (ValueError, IndexError):
            return None
        if not (1 <= year <= 9999):
            return None
        month = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 1
        day = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 1
        if not (1 <= month <= 12):
            month = 1
        if not (1 <= day <= 31):
            day = 1
        try:
            return date(year, month, day)
        except ValueError:
            # 例如 2 月 30 日等非法组合，回退到该月 1 日
            try:
                return date(year, month, 1)
            except ValueError:
                return None

    return None


def _is_fresh(evidence: dict, now: datetime) -> bool:
    """publish_date 是否落在近 RADAR_FRESH_DAYS 天内。缺失/无法解析视为不新鲜。"""
    pub = _parse_publish_date(evidence.get("publish_date"))
    if pub is None:
        return False

    today = now.date()
    delta_days = (today - pub).days
    # 落在 [今天-窗口, 今天] 之间视为新鲜；未来日期（delta<0）也接受为新鲜
    return delta_days <= RADAR_FRESH_DAYS


def _is_quality(evidence: dict) -> bool:
    """质量达标：evidence_level 属于 RADAR_MIN_LEVELS 或 source_type 属于 RADAR_FRESH_SOURCES。"""
    evidence_level = _clean_str(evidence.get("evidence_level")).lower()
    source_type = _clean_str(evidence.get("source_type")).lower()
    return evidence_level in RADAR_MIN_LEVELS or source_type in RADAR_FRESH_SOURCES


def is_new_progress(evidence: dict, now=None) -> bool:
    """
    判定一条证据是否为值得推送的新进展（R5.1）。

    条件 = 质量达标 且 新鲜：
    - 质量达标：evidence_level ∈ RADAR_MIN_LEVELS（high/moderate）
      或 source_type ∈ RADAR_FRESH_SOURCES（guide/trial/meeting）。
    - 新鲜：publish_date 落在近 RADAR_FRESH_DAYS 天内；缺失或无法解析
      视为不新鲜 → False。

    参数：
    - now: 便于测试注入的当前时间，默认 datetime.now()。

    纯函数，稳健处理缺失字段与异常输入，不抛异常。
    """
    if not isinstance(evidence, dict):
        return False

    if now is None:
        now = datetime.now()
    elif isinstance(now, date) and not isinstance(now, datetime):
        now = datetime(now.year, now.month, now.day)

    return _is_quality(evidence) and _is_fresh(evidence, now)
