from __future__ import annotations

import json
import re
from typing import Any, Optional

import httpx
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.core.logging import logger
from backend.app.models import SystemStateRow

SYSTEM_PROMPT = """你是中国A股投研助手。根据新闻，给出可能受影响的A股标的及短线涨跌倾向。
硬性要求：
1. 只输出 JSON 数组，不要 Markdown。
2. 每项字段：symbol(6位A股代码), direction(UP|DOWN|FLAT), confidence(0-1), sector(行业中文), reason(一两句中文)。
3. 无法映射到具体股票的新闻不要编造代码。
4. 最多返回 8 条，按置信度排序。
5. 不要推荐 ST/*ST；不要推荐无法交易的标的。
"""


def load_llm_settings(db: Optional[Session] = None) -> dict[str, str]:
    settings = get_settings()
    out = {
        "api_key": settings.llm_api_key or "",
        "base_url": (settings.llm_base_url or "https://api.openai.com/v1").rstrip("/"),
        "model": settings.llm_model or "gpt-4o-mini",
    }
    if db is not None:
        row = db.get(SystemStateRow, "llm_config")
        if row and isinstance(row.value, dict):
            if row.value.get("api_key"):
                out["api_key"] = str(row.value["api_key"])
            if row.value.get("base_url"):
                out["base_url"] = str(row.value["base_url"]).rstrip("/")
            if row.value.get("model"):
                out["model"] = str(row.value["model"])
    return out


def save_llm_settings(db: Session, api_key: str, base_url: str, model: str) -> dict[str, str]:
    row = db.get(SystemStateRow, "llm_config")
    value = {
        "api_key": api_key,
        "base_url": (base_url or "").rstrip("/"),
        "model": model,
    }
    if row is None:
        db.add(SystemStateRow(key="llm_config", value=value))
    else:
        # 空 key 表示保留原密钥
        if not api_key and isinstance(row.value, dict):
            value["api_key"] = row.value.get("api_key") or ""
        row.value = value
    db.commit()
    return {
        "api_key": "***" if value.get("api_key") else "",
        "base_url": value["base_url"],
        "model": value["model"],
        "configured": bool(value.get("api_key")),
    }


def _extract_json_array(text: str) -> list[dict[str, Any]]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]
        if isinstance(data, dict) and isinstance(data.get("items"), list):
            return [x for x in data["items"] if isinstance(x, dict)]
    except json.JSONDecodeError:
        pass
    m = re.search(r"\[[\s\S]*\]", text)
    if not m:
        return []
    try:
        data = json.loads(m.group(0))
        return [x for x in data if isinstance(x, dict)] if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


def normalize_symbol(raw: str) -> Optional[str]:
    digits = re.sub(r"\D", "", str(raw or ""))
    if len(digits) >= 6:
        code = digits[-6:]
        if code[0] in {"0", "3", "6"}:
            return code
    return None


def predict_from_news(
    db: Session,
    news: list[dict[str, Any]],
    focus_symbols: Optional[list[str]] = None,
) -> list[dict[str, Any]]:
    cfg = load_llm_settings(db)
    if not cfg.get("api_key"):
        raise RuntimeError("未配置 LLM_API_KEY（可在情报交易页填写）")

    timeout_s = float(get_settings().llm_timeout_seconds or 180.0)
    # 控制提示词体积，降低慢模型/跨境链路超时概率
    news_n = min(20, len(news))
    bullet = []
    for i, n in enumerate(news[:news_n], 1):
        bullet.append(f"{i}. [{n.get('source')}] {n.get('title')} | {n.get('summary', '')[:120]}")
    user = "新闻列表：\n" + "\n".join(bullet) + "\n\n请输出 JSON 数组。"
    if focus_symbols:
        sample = ",".join(focus_symbols[:40])
        user += f"\n\n当前可交易热点池（优先从中选，不要编造池外代码）：{sample}"

    url = f"{cfg['base_url']}/chat/completions"
    payload = {
        "model": cfg["model"],
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user},
        ],
    }
    headers = {"Authorization": f"Bearer {cfg['api_key']}", "Content-Type": "application/json"}
    timeout = httpx.Timeout(timeout_s, connect=20.0)
    last_exc: Optional[Exception] = None
    body = None
    for attempt in range(2):
        try:
            with httpx.Client(timeout=timeout) as client:
                resp = client.post(url, headers=headers, json=payload)
                resp.raise_for_status()
                body = resp.json()
            break
        except httpx.TimeoutException as exc:
            last_exc = exc
            logger.warning("llm timeout attempt=%s url=%s: %s", attempt + 1, url, exc)
        except httpx.HTTPStatusError as exc:
            detail = ""
            try:
                detail = exc.response.text[:300]
            except Exception:  # noqa: BLE001
                pass
            raise RuntimeError(f"LLM 接口错误 HTTP {exc.response.status_code}: {detail or exc}") from exc
        except httpx.HTTPError as exc:
            last_exc = exc
            logger.warning("llm http error attempt=%s: %s", attempt + 1, exc)
    if body is None:
        raise RuntimeError(
            f"LLM 请求超时/失败（{timeout_s:.0f}s，已重试）。请检查网络、LLM_BASE_URL={cfg['base_url']}，"
            f"或在 .env 增大 LLM_TIMEOUT_SECONDS。"
        ) from last_exc

    content = body["choices"][0]["message"]["content"]
    raw_items = _extract_json_array(content)
    out: list[dict[str, Any]] = []
    for it in raw_items:
        symbol = normalize_symbol(str(it.get("symbol") or ""))
        if not symbol:
            continue
        direction = str(it.get("direction") or "FLAT").upper()
        if direction not in {"UP", "DOWN", "FLAT"}:
            direction = "FLAT"
        try:
            conf = float(it.get("confidence") or 0)
        except (TypeError, ValueError):
            conf = 0.0
        conf = max(0.0, min(1.0, conf))
        out.append(
            {
                "symbol": symbol,
                "direction": direction,
                "confidence": conf,
                "sector": str(it.get("sector") or "")[:64],
                "reason": str(it.get("reason") or "")[:500],
            }
        )
    logger.info("llm predictions=%s", len(out))
    return out
