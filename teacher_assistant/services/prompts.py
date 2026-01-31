from __future__ import annotations

from pathlib import Path
from typing import Optional

BASE = Path(__file__).resolve().parents[2] / "docs" / "subjects"


def get_prompt_for_subject(subject: str) -> Optional[str]:
    """Return the prompts.md content for the given subject, or None if missing."""
    if not subject:
        return None
    safe = subject.replace("/", "_")
    p = BASE / safe / "prompts.md"
    if not p.exists():
        return None
    try:
        return p.read_text(encoding="utf-8")
    except Exception:
        return None


__all__ = ["get_prompt_for_subject"]
