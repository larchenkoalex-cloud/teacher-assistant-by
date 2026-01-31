from __future__ import annotations

from pathlib import Path
from typing import List, Optional
import re

BASE = Path(__file__).resolve().parents[2] / "docs" / "subjects"


def _parse_markdown_table_topics(text: str) -> List[str]:
    lines = [ln.rstrip() for ln in text.splitlines()]
    topics: List[str] = []
    for ln in lines:
        # table row with pipes and at least two columns
        if ln.strip().startswith("|") and '|' in ln[1:]:
            parts = [p.strip() for p in ln.split("|")]
            # drop empty leading/trailing from split
            parts = [p for p in parts if p != '']
            if len(parts) >= 2:
                # assume second column is 'Тема/произведение' or similar
                topic = parts[1]
                # skip header/separator rows
                if re.match(r'^-+$', topic) or topic.lower().startswith('тема'):
                    continue
                if topic:
                    topics.append(topic)
    return topics


def _fallback_extract_topics(text: str) -> List[str]:
    topics: List[str] = []
    for ln in text.splitlines():
        ln = ln.strip()
        if not ln:
            continue
        # lines that look like 'Сентябрь | Тема' already covered; try dash or plain 'Месяц — Тема'
        m = re.match(r'^[\-|•\*\d\.]?\s*(?:[А-Яа-яA-Za-z]+)\s*[\|\-—]\s*(.+)$', ln)
        if m:
            topics.append(m.group(1).strip())
            continue
        # headings as fallback
        if ln.startswith('#'):
            continue
        # short lines (<=60 chars) could be topics
        if 3 < len(ln) < 120 and re.search(r'[а-яА-Яa-zA-Z]', ln):
            topics.append(ln)
    return topics


def get_calendar_topics_for_subject(subject: str) -> List[str]:
    """Возвращает список тем из `calendar_planning.md` для предмета.

    Простая логика: сначала парсим таблицы Markdown, затем fallback на простые строки.
    """
    if not subject:
        return []
    safe = subject.replace('/', '_')
    p = BASE / safe / 'calendar_planning.md'
    if not p.exists():
        return []
    try:
        txt = p.read_text(encoding='utf-8')
    except Exception:
        return []

    topics = _parse_markdown_table_topics(txt)
    if topics:
        # dedupe while preserving order
        seen = set()
        out = []
        for t in topics:
            if t not in seen:
                seen.add(t)
                out.append(t)
        return out

    fb = _fallback_extract_topics(txt)
    # dedupe
    seen = set()
    out = []
    for t in fb:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


__all__ = ["get_calendar_topics_for_subject"]
