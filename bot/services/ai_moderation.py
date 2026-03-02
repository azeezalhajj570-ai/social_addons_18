from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass

from aiohttp import ClientSession, ClientTimeout
from loguru import logger

from bot.core.config import settings

SYSTEM_PROMPT = (
    "You are a strict Telegram moderator classifier. "
    "Decide whether a message is promotional/advertising/spam and should be deleted. "
    "Return only compact JSON: "
    '{"delete": boolean, "confidence": number, "category": "promotion|safe|unclear", "reason": "short"}'
)


@dataclass(frozen=True)
class AIModerationDecision:
    should_delete: bool
    confidence: float | None
    category: str
    reason: str | None


def _extract_json_object(content: str) -> str | None:
    start = content.find("{")
    end = content.rfind("}")
    if start < 0 or end < 0 or end <= start:
        return None
    return content[start : end + 1]


def _parse_decision(content: str) -> AIModerationDecision:
    parsed_content = _extract_json_object(content) or content
    payload = json.loads(parsed_content)

    category = str(payload.get("category", "unclear")).strip().lower()
    reason = payload.get("reason")
    confidence_raw = payload.get("confidence")
    confidence = float(confidence_raw) if isinstance(confidence_raw, int | float | str) else None
    delete_flag = bool(payload.get("delete", False))

    if confidence is not None and confidence < settings.AI_MODERATION_CONFIDENCE_THRESHOLD:
        delete_flag = False

    return AIModerationDecision(
        should_delete=delete_flag,
        confidence=confidence,
        category=category,
        reason=str(reason).strip() if reason is not None else None,
    )


def enabled() -> bool:
    return settings.AI_MODERATION_ENABLED and bool(settings.AI_MODERATION_API_KEY)


def _build_user_prompt(message_text: str, matched_keyword: str, chat_id: int, user_id: int) -> str:
    return (
        f"chat_id={chat_id}\n"
        f"user_id={user_id}\n"
        f"matched_filter_keyword={matched_keyword}\n"
        f"message:\n{message_text}"
    )


async def _request_openai_compatible(
    *,
    client: ClientSession,
    user_prompt: str,
) -> str:
    url = f"{settings.AI_MODERATION_BASE_URL.rstrip('/')}/chat/completions"
    payload = {
        "model": settings.AI_MODERATION_MODEL,
        "temperature": 0,
        "max_tokens": 80,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    }
    headers = {
        "Authorization": f"Bearer {settings.AI_MODERATION_API_KEY}",
        "Content-Type": "application/json",
    }
    async with client.post(url, headers=headers, json=payload) as response:
        response.raise_for_status()
        data = await response.json()
    return str(data["choices"][0]["message"]["content"])


async def _request_gemini(
    *,
    client: ClientSession,
    user_prompt: str,
) -> str:
    base = settings.AI_MODERATION_BASE_URL.rstrip("/")
    url = f"{base}/models/{settings.AI_MODERATION_MODEL}:generateContent?key={settings.AI_MODERATION_API_KEY}"
    payload = {
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
        "generationConfig": {
            "temperature": 0,
            "maxOutputTokens": 120,
            "responseMimeType": "application/json",
        },
    }
    async with client.post(url, json=payload) as response:
        response.raise_for_status()
        data = await response.json()

    candidates = data.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise ValueError("Gemini response missing candidates")
    first = candidates[0]
    content = first.get("content") if isinstance(first, Mapping) else None
    parts = content.get("parts") if isinstance(content, Mapping) else None
    if not isinstance(parts, list) or not parts:
        raise ValueError("Gemini response missing parts")
    text_part = parts[0]
    if not isinstance(text_part, Mapping) or "text" not in text_part:
        raise ValueError("Gemini response missing text")
    return str(text_part["text"])


async def evaluate_filter_hit(
    *,
    message_text: str,
    matched_keyword: str,
    chat_id: int,
    user_id: int,
) -> AIModerationDecision:
    if not enabled() or not message_text.strip():
        return AIModerationDecision(False, None, "disabled", None)

    timeout = ClientTimeout(total=float(settings.AI_MODERATION_TIMEOUT_SECONDS))
    user_prompt = _build_user_prompt(message_text, matched_keyword, chat_id, user_id)
    provider = settings.AI_MODERATION_PROVIDER.strip().lower()

    try:
        async with ClientSession(timeout=timeout) as client:
            if provider == "gemini":
                content = await _request_gemini(client=client, user_prompt=user_prompt)
            elif provider == "openai":
                content = await _request_openai_compatible(client=client, user_prompt=user_prompt)
            else:
                logger.warning("unsupported ai moderation provider: {}", settings.AI_MODERATION_PROVIDER)
                return AIModerationDecision(False, None, "unsupported_provider", None)
    except Exception as exc:
        logger.warning("ai moderation request failed chat={} user={} err={}", chat_id, user_id, exc)
        return AIModerationDecision(False, None, "error", None)

    try:
        return _parse_decision(content)
    except Exception as exc:
        logger.warning("ai moderation parse failed chat={} user={} err={}", chat_id, user_id, exc)
        return AIModerationDecision(False, None, "parse_error", None)
