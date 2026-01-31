import re
from bs4 import BeautifulSoup


def normalize_lists_in_html(html_text: str) -> str:
    """Преобразует последовательные <p>-строки с маркерами в корректные <ul>/<ol>.

    Примеры входа:
      <p>- первый пункт</p>
      <p>- второй пункт</p>

    Функция объединит их в:
      <ul><li>первый пункт</li><li>второй пункт</li></ul>

    Зачем: Quill иногда интерпретирует "псевдосписки" как абзацы и
    вставляет лишние пустые строки.
    """
    if not html_text:
        return ""

    soup = BeautifulSoup(html_text, "html.parser")
    container = soup.body if soup.body else soup

    children = list(container.children)
    i = 0
    while i < len(children):
        node = children[i]
        if getattr(node, "name", None) == "p":
            text = node.get_text()
            m = re.match(r"^\s*((\d+\.)|[-*•])\s+", text)
            if m:
                is_numbered = bool(m.group(2))

                items = []
                j = i
                while j < len(children):
                    nd = children[j]
                    if getattr(nd, "name", None) != "p":
                        break
                    t = nd.get_text()
                    mm = re.match(r"^\s*((\d+\.)|[-*•])\s+(.*)$", t)
                    if not mm:
                        break
                    items.append(nd)
                    j += 1

                if items:
                    list_tag = soup.new_tag("ol" if is_numbered else "ul")
                    for pnode in items:
                        li = soup.new_tag("li")
                        inner_html = "".join(str(c) for c in pnode.contents)
                        inner_html = re.sub(r"^\s*(?:\d+\.\s+|[-*•]\s+)", "", inner_html, count=1)
                        fragment = BeautifulSoup(inner_html, "html.parser")
                        for c in fragment.contents:
                            li.append(c)
                        list_tag.append(li)

                    first = items[0]
                    first.replace_with(list_tag)
                    for k in items[1:]:
                        k.extract()

                    children = list(container.children)
                    i += 1
                    continue
        i += 1

    return str(soup)


def sanitize_html_for_quill(html_text: str) -> str:
    """Подготовить HTML перед загрузкой в Quill.

    - Убираем межтеговые переводы строк/пробелы (например "</p>\n<p>")
      чтобы Quill не вставлял пустые параграфы между блоками.
    - Удаляем полностью пустые параграфы вида `<p>\s*</p>` и `<p><br></p>`.
    - Нормализуем "псевдо-списки" (последовательные <p>- ...</p>).
    """
    if not html_text:
        return ""

    html = re.sub(r"<p>(?:\s|&nbsp;|<br\s*/?>)*</p>", "", html_text, flags=re.IGNORECASE)
    html = re.sub(r">\s+<", "><", html)
    html = re.sub(r"(?:<p>\s*</p>\s*){2,}", "", html, flags=re.IGNORECASE)

    html = normalize_lists_in_html(html)

    return html.strip()
