from __future__ import annotations

import json
from typing import Callable, Optional

import requests

OPENROUTER_CHAT_COMPLETIONS_URL = "https://openrouter.ai/api/v1/chat/completions"


def build_headers(api_key: str, *, title: str = "Teacher Assistant") -> dict:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://teacher-assistant.streamlit.app",
        "X-Title": title,
    }


def chat_completions(
    *,
    api_key: str,
    messages: list,
    model: str = "deepseek/deepseek-chat",
    temperature: float = 0.7,
    max_tokens: int = 2000,
    timeout: int = 60,
    base_url: str = OPENROUTER_CHAT_COMPLETIONS_URL,
) -> str:
    resp = requests.post(
        base_url,
        headers=build_headers(api_key),
        json={
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def stream_chat_completions(
    *,
    api_key: str,
    messages: list,
    on_update: Optional[Callable[[str], None]] = None,
    model: str = "deepseek/deepseek-chat",
    temperature: float = 0.7,
    max_tokens: int = 2000,
    timeout: int = 60,
    base_url: str = OPENROUTER_CHAT_COMPLETIONS_URL,
) -> str:
    """Стриминг ответа (SSE) с OpenRouter.

    - Возвращает полный текст
    - При каждом обновлении вызывает `on_update(full_text)`

    Если провайдер не отдает `text/event-stream`, делает fallback на обычный JSON.
    """

    buffer = ""
    data = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": True,
    }

    resp = requests.post(base_url, headers=build_headers(api_key), json=data, timeout=timeout, stream=True)
    resp.raise_for_status()

    # Принудительно декодируем как UTF-8 — предотвращает mojibake.
    resp.encoding = "utf-8"

    content_type = (resp.headers.get("content-type") or "").lower()
    if "text/event-stream" not in content_type:
        result = resp.json()
        return result["choices"][0]["message"]["content"]

    for chunk in resp.iter_lines(decode_unicode=True):
        if not chunk:
            continue
        line = chunk.strip()
        if line.startswith("data:"):
            line = line[len("data:") :].strip()
        if not line or line == "[DONE]":
            continue

        try:
            payload = json.loads(line)
        except Exception:
            continue

        for choice in payload.get("choices", []):
            delta = choice.get("delta") or {}
            piece = delta.get("content")
            if piece:
                buffer += piece

        if on_update:
            on_update(buffer)

    return buffer
