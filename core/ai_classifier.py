"""AI-enhanced bid classification using OpenAI or Anthropic APIs.

Falls back gracefully to keyword-based filtering when AI is unavailable.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from core.models import BidRecord

logger = logging.getLogger("bid-monitor.ai")

CLASSIFICATION_PROMPT = """\
你是一位台灣政府採購標案分析專家。請根據以下標案資訊進行分析判斷。

標案資訊：
- 機關名稱：{org_name}
- 標案名稱：{title}
- 摘要：{summary}
- 類別：{category}
- 金額：{amount}
- 預算金額：{budget_amount}
- 截止投標：{bid_deadline}
- 開標時間：{bid_opening_time}

請以 JSON 格式回覆以下分析結果：
{{
  "is_educational": <bool>,
  "edu_score": <0-10 整數>,
  "edu_reason": "<為何判定為教育單位或非教育單位>",
  "is_it_related": <bool>,
  "it_score": <0-10 整數>,
  "it_reason": "<為何判定為資訊相關或非資訊相關>",
  "priority": "<high|medium|low>",
  "priority_reason": "<優先度判定理由>",
  "ai_summary": "<30 字內精要摘要>",
  "suggested_tags": ["<標籤1>", "<標籤2>"]
}}

判斷標準：
1. 教育單位：包含大學、學院、學校、國中小、高中職、教育局/處，也包含間接相關（如「市政府教育局委辦」、「校園」等）

2. 資訊相關：包含資訊設備、資訊服務、電腦、伺服器、網路、雲端、資安、軟體、機房，也包含新興詞彙如「數位轉型」、「智慧校園」、「AI」、「大數據」等

3. 優先度判斷（綜合考量）：
   - **單位層級權重**：大學 > 教育局 > 高中職 > 國中小
   - **金額分層**：
     * >1000萬 = 極高 (high)
     * 500-1000萬 = 高 (high)
     * 100-500萬 = 中 (medium)
     * <100萬 = 低 (low 或 medium)
   - **主題相關性**：資安/雲端 > 硬體設備 > 軟體授權 > 其他
   - **時效性**：截止日期7天內 = 加急，可提升優先度

僅回覆 JSON，不要加任何其他文字。"""


@dataclass(slots=True)
class AIClassification:
    is_educational: bool = False
    edu_score: int = 0
    edu_reason: str = ""
    is_it_related: bool = False
    it_score: int = 0
    it_reason: str = ""
    priority: str = "medium"
    priority_reason: str = ""
    ai_summary: str = ""
    suggested_tags: list[str] | None = None
    raw_response: str = ""
    model_used: str = ""
    error: str = ""


def classify_bid(
    record: BidRecord,
    *,
    openai_client: Any | None = None,
    anthropic_client: Any | None = None,
    model: str = "",
    log: Any | None = None,
) -> AIClassification:
    """Classify a single bid record using AI. Returns AIClassification."""
    log = log or logger
    prompt = CLASSIFICATION_PROMPT.format(
        org_name=record.organization,
        title=record.title,
        summary=record.summary or "(無)",
        category=record.category or "(無)",
        amount=f"NT$ {int(record.amount_value):,}" if record.amount_value else record.amount_raw or "(未公開)",
        budget_amount=record.budget_amount or "(無提供)",
        bid_deadline=record.bid_deadline or "(無提供)",
        bid_opening_time=record.bid_opening_time or "(無提供)",
    )

    if openai_client is not None:
        return _classify_via_openai(openai_client, prompt, model or "gpt-4o-mini", log)
    if anthropic_client is not None:
        return _classify_via_anthropic(anthropic_client, prompt, model or "claude-sonnet-4-20250514", log)

    return AIClassification(error="no_ai_client_available")


def classify_bids_batch(
    records: list[BidRecord],
    *,
    openai_client: Any | None = None,
    anthropic_client: Any | None = None,
    model: str = "",
    log: Any | None = None,
) -> list[AIClassification]:
    """Classify multiple bids. Falls back gracefully on per-item errors."""
    log = log or logger
    results: list[AIClassification] = []
    for i, record in enumerate(records):
        try:
            result = classify_bid(
                record,
                openai_client=openai_client,
                anthropic_client=anthropic_client,
                model=model,
                log=log,
            )
            results.append(result)
        except Exception as exc:
            log.warning("ai_classify_item_failed", extra={"index": i, "error": str(exc)})
            results.append(AIClassification(error=str(exc)))
    return results


def _classify_via_openai(client: Any, prompt: str, model: str, log: Any) -> AIClassification:
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        max_tokens=500,
    )
    raw = response.choices[0].message.content.strip()
    log.info("openai_classify_done", extra={"model": model})
    return _parse_response(raw, model_used=f"openai/{model}")


def _classify_via_anthropic(client: Any, prompt: str, model: str, log: Any) -> AIClassification:
    response = client.messages.create(
        model=model,
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = response.content[0].text.strip()
    log.info("anthropic_classify_done", extra={"model": model})
    return _parse_response(raw, model_used=f"anthropic/{model}")


def _parse_response(raw: str, model_used: str) -> AIClassification:
    # Strip markdown code fences if present
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [ln for ln in lines if not ln.strip().startswith("```")]
        text = "\n".join(lines)

    data = json.loads(text)
    return AIClassification(
        is_educational=bool(data.get("is_educational", False)),
        edu_score=int(data.get("edu_score", 0)),
        edu_reason=str(data.get("edu_reason", "")),
        is_it_related=bool(data.get("is_it_related", False)),
        it_score=int(data.get("it_score", 0)),
        it_reason=str(data.get("it_reason", "")),
        priority=str(data.get("priority", "medium")),
        priority_reason=str(data.get("priority_reason", "")),
        ai_summary=str(data.get("ai_summary", "")),
        suggested_tags=data.get("suggested_tags"),
        raw_response=raw,
        model_used=model_used,
    )


def build_ai_clients(settings: Any) -> tuple[Any | None, Any | None]:
    """Build OpenAI and/or Anthropic clients from settings. Returns (openai_client, anthropic_client)."""
    openai_client = None
    anthropic_client = None

    openai_api_key = getattr(settings, "openai_api_key", "")
    anthropic_api_key = getattr(settings, "anthropic_api_key", "")

    if openai_api_key:
        try:
            from openai import OpenAI
            openai_client = OpenAI(api_key=openai_api_key)
            logger.info("openai_client_initialized")
        except ImportError:
            logger.warning("openai package not installed, skipping OpenAI client")
        except Exception as exc:
            logger.warning("openai_client_init_failed", extra={"error": str(exc)})

    if anthropic_api_key:
        try:
            from anthropic import Anthropic
            anthropic_client = Anthropic(api_key=anthropic_api_key)
            logger.info("anthropic_client_initialized")
        except ImportError:
            logger.warning("anthropic package not installed, skipping Anthropic client")
        except Exception as exc:
            logger.warning("anthropic_client_init_failed", extra={"error": str(exc)})

    return openai_client, anthropic_client
