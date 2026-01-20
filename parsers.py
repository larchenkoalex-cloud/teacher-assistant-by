from pathlib import Path
from typing import List

try:
    import docx  # type: ignore
except Exception:
    docx = None

try:
    from PyPDF2 import PdfReader  # type: ignore
except Exception:
    PdfReader = None


def extract_topics_from_docx(path: Path, max_topics: int = 20) -> List[str]:
    """Пытается вытащить темы из DOCX по заголовкам и коротким абзацам."""

    if docx is None:
        return []

    topics: List[str] = []
    doc = docx.Document(path)

    def _collect_from_paragraphs(paragraphs) -> None:
        for para in paragraphs:
            style_name = getattr(para.style, "name", "")
            text = para.text.strip()
            if not text:
                continue
            if style_name and "Heading" in style_name:
                topics.append(text)
            elif len(text) < 80 and text.endswith(":"):
                topics.append(text.rstrip(":"))

    # 1) Обычные абзацы
    _collect_from_paragraphs(doc.paragraphs)

    # 2) Текст внутри таблиц (часто КТП оформлены таблицами)
    for table in getattr(doc, "tables", []):
        for row in table.rows:
            for cell in row.cells:
                _collect_from_paragraphs(cell.paragraphs)

    if not topics:
        # Fallback: короткие абзацы (в том числе из таблиц)
        def _collect_short(paragraphs) -> None:
            for para in paragraphs:
                t = para.text.strip()
                if t and 2 < len(t) < 60:
                    topics.append(t)

        _collect_short(doc.paragraphs)
        for table in getattr(doc, "tables", []):
            for row in table.rows:
                for cell in row.cells:
                    _collect_short(cell.paragraphs)
    # уникальные, максимум max_topics
    seen = set()
    result: List[str] = []
    for t in topics:
        if t not in seen:
            seen.add(t)
            result.append(t)
        if len(result) >= max_topics:
            break
    return result


def extract_topics_from_pdf(path: Path, max_topics: int = 20) -> List[str]:
    """Пытается вытащить темы из PDF по первым строкам страниц."""

    if PdfReader is None:
        return []

    reader = PdfReader(str(path))
    topics: List[str] = []
    for page in reader.pages[: max_topics]:
        text = page.extract_text() or ""
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        if lines:
            topics.append(lines[0])
    # уникальные
    seen = set()
    result: List[str] = []
    for t in topics:
        if t not in seen:
            seen.add(t)
            result.append(t)
    return result


def extract_topics(path: Path, max_topics: int = 20) -> List[str]:
    suffix = path.suffix.lower()
    if suffix == ".docx":
        return extract_topics_from_docx(path, max_topics=max_topics)
    if suffix == ".pdf":
        return extract_topics_from_pdf(path, max_topics=max_topics)
    return []


def extract_full_text(path: Path) -> List[str]:
    """Возвращает список строк полного текста документа (docx / pdf).

    Удобно для отображения и ручной пометки строк как тем.
    """
    suffix = path.suffix.lower()
    lines: List[str] = []
    if suffix == ".docx":
        if docx is None:
            return []
        doc = docx.Document(path)

        # Сначала абзацы в порядке документа
        for para in doc.paragraphs:
            t = para.text.strip()
            if t:
                lines.append(t)

        # Затем содержимое таблиц (если есть)
        for table in getattr(doc, "tables", []):
            for row in table.rows:
                for cell in row.cells:
                    for para in cell.paragraphs:
                        t = para.text.strip()
                        if t:
                            lines.append(t)

    elif suffix == ".pdf":
        if PdfReader is None:
            return []
        reader = PdfReader(str(path))
        for page in reader.pages:
            text = page.extract_text() or ""
            for ln in text.splitlines():
                t = ln.strip()
                if t:
                    lines.append(t)

    return lines
