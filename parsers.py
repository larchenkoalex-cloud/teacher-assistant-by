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
    for para in doc.paragraphs:
        style_name = getattr(para.style, "name", "")
        text = para.text.strip()
        if not text:
            continue
        if style_name and "Heading" in style_name:
            topics.append(text)
        elif len(text) < 80 and text.endswith(":"):
            topics.append(text.rstrip(":"))
    if not topics:
        # Fallback: короткие абзацы
        for para in doc.paragraphs:
            t = para.text.strip()
            if t and len(t) < 60:
                topics.append(t)
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
