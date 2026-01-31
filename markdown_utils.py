def markdown_to_html(md: str) -> str:
    import markdown

    if md is None:
        return ""

    return markdown.markdown(
        md,
        extensions=["extra", "sane_lists"],
        output_format="html5",
    )
