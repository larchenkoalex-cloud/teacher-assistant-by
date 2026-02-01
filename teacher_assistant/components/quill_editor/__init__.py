from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

import streamlit as st
import streamlit.components.v1 as components


_FRONTEND_DIR = Path(__file__).parent / "frontend"

_quill_editor = components.declare_component(
    "teacher_assistant_quill_editor",
    path=str(_FRONTEND_DIR),
)


def quill_editor(
    *,
    value: str,
    height: int = 420,
    key: Optional[str] = None,
    apply_replace: Optional[Dict[str, Any]] = None,
  request_selection: Optional[Dict[str, Any]] = None,
    placeholder: str = "",
) -> Any:
    """Quill editor with context-menu selection events.

    Returns either:
      - dict event: {type: 'content'|'replace_request', ...}
      - or None

    `apply_replace` format:
      {"id": int, "range": {"index": int, "length": int}, "text": str}
    """

    # Streamlit components re-run often; keep payload small.
    return _quill_editor(
        value=value or "",
        height=height,
        placeholder=placeholder,
        applyReplace=apply_replace,
        requestSelection=request_selection,
        key=key,
      # ВАЖНО: не возвращаем "фейковый" content по умолчанию.
      # Иначе при rerun с applyReplace сервер может увидеть этот default-content,
      # сбросить apply-флаг раньше времени и автозамена будет срабатывать
      # только после следующего взаимодействия пользователя.
      default={"type": "noop"},
    )
