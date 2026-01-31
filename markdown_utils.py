def markdown_to_html(md: str) -> str:
    import markdown

    return markdown.markdown(
        md,
        extensions=["extra", "sane_lists"],
        output_format="html5",
    )
