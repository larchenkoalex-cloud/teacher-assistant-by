def normalize_ai_markdown(md: str) -> str:
    if not md:
        return ""

    md = (
        md.replace("\r\n", "\n")
          .replace("\r", "\n")
          .replace("\u200b", "")
          .replace("\xa0", " ")
    )

    result = []

    for line in md.split("\n"):
        stripped = line.strip()

        # ❌ пустые пункты списков
        if stripped in ("-", "*", "•"):
            continue

        # ❌ вложенные списки — запрещаем
        if line.startswith(("  -", "  *", "\t-", "\t*")):
            line = stripped  # разворачиваем в обычный список

        result.append(line.lstrip())

    text = "\n".join(result)

    # ❌ больше двух пустых строк подряд
    while "\n\n\n" in text:
        text = text.replace("\n\n\n", "\n\n")

    return text.strip()
