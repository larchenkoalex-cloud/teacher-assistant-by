def normalize_ai_markdown(md: str) -> str:
    if not md:
        return ""

    md = (
        md.replace("\r\n", "\n")
          .replace("\r", "\n")
          .replace("\u200b", "")
          .replace("\xa0", " ")
    )

    while "\n\n\n" in md:
        md = md.replace("\n\n\n", "\n\n")

    return md.strip()
