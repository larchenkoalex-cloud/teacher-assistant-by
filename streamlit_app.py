import os
import re
import html
import time
from io import BytesIO
from datetime import datetime
from pathlib import Path

import requests
import streamlit as st
from bs4 import BeautifulSoup, NavigableString

try:
    from streamlit_quill import st_quill
except Exception:  # pragma: no cover
    st_quill = None

from teacher_assistant.services import (
    LessonPlan,
    create_lesson_plan,
    init_db,
    list_lesson_plans,
    create_user,
    get_user_by_username,
    list_materials,
    delete_material,
    create_material,
)
from teacher_assistant.services.calendar import get_calendar_topics_for_subject
from passlib.hash import bcrypt

from parsers import extract_topics, extract_full_text, extract_topics_from_pdf_advanced
import json
from text_normalizer import normalize_ai_markdown
from markdown_utils import markdown_to_html

# Переезд логики в пакет `teacher_assistant/` (для масштабирования проекта)
from teacher_assistant.ai import openrouter as openrouter_client
from teacher_assistant.app.streamlit_helpers import safe_rerun
from teacher_assistant.utils import quill_html as quill_html_utils

try:
    from teacher_assistant.components.quill_editor import quill_editor
except Exception:  # pragma: no cover
    quill_editor = None


def generate_with_deepseek(api_key: str, prompt: str, model: str = "deepseek/deepseek-chat") -> dict:
    """Универсальная функция для запросов к DeepSeek через OpenRouter"""
    try:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://teacher-assistant.streamlit.app",
            "X-Title": "Teacher Assistant"
        }
        
        data = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7,
            "max_tokens": 2000
        }
        
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=data,
            timeout=60
        )
        
        response.raise_for_status()
        return response.json()
        
    except Exception as e:
        return {"error": str(e), "choices": [{"message": {"content": f"Ошибка: {e}"}}]}


IS_DEV_ADMIN = True  # в режиме разработки считаем текущего пользователя администратором

SUBJECTS = [
    "Математика",
    "Русский язык",
    "Литература",
    "Музыка",
    "Белорусский язык",
    "Английский язык",
    "Иностранный язык (английский)",
    "Информатика",
    "Физика",
    "Химия",
    "Биология",
    "История",
    "Обществоведение",
    "География",
]

GRADES = [f"{i} класс" for i in range(1, 12)]

st.set_page_config(page_title="Teacher Assistant", layout="wide")

# Инициализация БД (SQLite по умолчанию, можно заменить на Postgres через DATABASE_URL)
init_db()

st.title("Teacher Assistant — помощник для учителя")

# Sidebar settings header
st.sidebar.header("Настройки DeepSeek (OpenRouter)")

# Читаем ключ OpenRouter (не DeepSeek напрямую!)
_secrets_key = None
try:
    _secrets_key = st.secrets.get("OPENROUTER_API_KEY")  # Изменили имя!
except Exception:
    _secrets_key = None
_env_key = os.getenv("OPENROUTER_API_KEY")  # Изменили имя!

api_key_input = st.sidebar.text_input("OpenRouter API key", type="password", 
                                      help="Ключ начинается с sk-or-v1-...")
api_key = _secrets_key or _env_key or api_key_input
try:
    # Сохраняем в session_state, чтобы другие блоки (inline AI и пр.) могли читать ключ
    st.session_state["api_key"] = api_key
except Exception:
    pass

# Фиксированный URL для OpenRouter (не настраиваемый)
DEEPSEEK_API_BASE = "https://openrouter.ai/api/v1/chat/completions"

# Показываем источник ключа
if api_key:
    if _secrets_key and api_key == _secrets_key:
        api_key_source = "st.secrets"
    elif _env_key and api_key == _env_key:
        api_key_source = "env"
    elif api_key_input and api_key == api_key_input:
        api_key_source = "sidebar"
    else:
        api_key_source = "unknown"
    st.sidebar.success(f"✅ Ключ загружен ({api_key_source})")
else:
    st.sidebar.warning("⚠️ Ключ OpenRouter не задан")

show_deepseek_debug = st.sidebar.checkbox("Показывать отладку API", value=False)

# Опция показа последних планов (по умолчанию скрыта)
show_recent_plans = st.sidebar.checkbox("Показывать последние сохранённые планы", value=False)

# Кнопка проверки подключения
if st.sidebar.button("Проверить подключение к API"):
    if not api_key:
        st.sidebar.error("Сначала введите API ключ")
    else:
        with st.sidebar.spinner("Проверяем..."):
            try:
                response = requests.post(
                    DEEPSEEK_API_BASE,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": "deepseek/deepseek-chat",
                        "messages": [{"role": "user", "content": "Ответь 'OK'"}],
                        "max_tokens": 10
                    },
                    timeout=10
                )
                if response.status_code == 200:
                    st.sidebar.success("✅ API работает!")
                else:
                    st.sidebar.error(f"❌ Ошибка API: {response.status_code}")
            except Exception as e:
                st.sidebar.error(f"❌ Ошибка: {e}")

# Переключение между пользовательским режимом и админ-панелью
app_mode = st.sidebar.radio("Режим", ["Пользовательский режим", "Админ-панель"])

# --- Простая аутентификация для педагогов (регистрация / вход)
if "user_id" not in st.session_state:
    st.session_state["user_id"] = None
    st.session_state["username"] = None

auth_mode = st.sidebar.selectbox("Аккаунт", ["Войти", "Регистрация", "Профиль"])
if auth_mode == "Регистрация":
    with st.sidebar.form("register_form"):
        reg_username = st.text_input("Логин")
        reg_email = st.text_input("Email (опционально)")
        reg_password = st.text_input("Пароль", type="password")
        reg_password2 = st.text_input("Повторите пароль", type="password")
        if st.form_submit_button("Зарегистрироваться"):
            if not reg_username or not reg_password:
                st.sidebar.warning("Укажите логин и пароль.")
            elif reg_password != reg_password2:
                st.sidebar.warning("Пароли не совпадают.")
            elif get_user_by_username(reg_username):
                st.sidebar.warning("Пользователь с таким логином уже существует.")
            else:
                pwd_hash = bcrypt.hash(reg_password)
                user = create_user(username=reg_username, email=reg_email or None, password_hash=pwd_hash)
                st.session_state["user_id"] = user.id
                st.session_state["username"] = user.username
                st.sidebar.success("Регистрация прошла успешно. Вы вошли как {}".format(user.username))

elif auth_mode == "Войти":
    with st.sidebar.form("login_form"):
        login_username = st.text_input("Логин")
        login_password = st.text_input("Пароль", type="password")
        if st.form_submit_button("Войти"):
            user = get_user_by_username(login_username)
            if not user:
                st.sidebar.error("Пользователь не найден.")
            else:
                try:
                    if bcrypt.verify(login_password, user.password_hash):
                        st.session_state["user_id"] = user.id
                        st.session_state["username"] = user.username
                        st.sidebar.success(f"Вы вошли как {user.username}")
                    else:
                        st.sidebar.error("Неверный пароль.")
                except Exception:
                    st.sidebar.error("Ошибка проверки пароля.")

else:  # Профиль
    if st.session_state.get("user_id"):
        st.sidebar.write(f"Вошли как: {st.session_state.get('username')}")
        if st.sidebar.button("Выйти"):
            st.session_state["user_id"] = None
            st.session_state["username"] = None
            st.sidebar.success("Вы вышли.")
    else:
        st.sidebar.info("Войдите или зарегистрируйтесь, чтобы публиковать материалы.")

current_user = None
if st.session_state.get("username"):
    current_user = get_user_by_username(st.session_state["username"])

materials_dir = Path(os.getenv("MATERIALS_DIR", "materials"))
materials_dir.mkdir(exist_ok=True)


def generate_lesson_plan_locally(subject: str, grade: str, topic: str, notes: str, class_level: str = None) -> str:
    """Локальная заготовка плана урока на случай отсутствия API."""

    header = (
        f"План урока по предмету: {subject} (класс: {grade})\n"
        f"Уровень подготовки класса: {class_level or 'средний'}\n"
        f"Тема: {topic}\n\n"
    )
    body = """Цели урока:
- сформировать понимание ключевых понятий по теме;
- развивать навыки самостоятельной работы и критического мышления;
- закрепить материал через практические задания.

Ход урока:
1. Организационный момент (2–3 мин).
2. Актуализация знаний (5–7 мин).
3. Объяснение нового материала (15–20 мин).
4. Закрепление (индивидуальные и групповые задания) (10–15 мин).
5. Рефлексия и подведение итогов (5 мин).
6. Домашнее задание.

Материалы и ресурсы:
- презентация/конспект для учителя;
- раздаточные материалы для учащихся;
- дополнительные ресурсы (ссылки, видео, интерактивы).
"""
    if notes:
        body += f"\nОсобенности класса / примечания учителя:\n{notes}\n"
    return header + body


def stream_generate_chat_via_api(*, messages: list, headers: dict, placeholder, model: str = "deepseek/deepseek-chat") -> str:
    """Потоково читает ответ (SSE) и обновляет placeholder; возвращает полный текст.

    Если провайдер не поддерживает SSE, делает обычный запрос и возвращает полный ответ.
    """
    # Вынесено в teacher_assistant.ai.openrouter (для повторного использования и тестирования)
    api_key = None
    try:
        auth = (headers or {}).get("Authorization") or ""
        if auth.startswith("Bearer "):
            api_key = auth[len("Bearer ") :].strip()
    except Exception:
        api_key = None

    if not api_key:
        return ""

    def _on_update(full_text: str) -> None:
        placeholder.markdown(_postprocess_plan_text(full_text))

    try:
        return openrouter_client.stream_chat_completions(
            api_key=api_key,
            messages=messages,
            on_update=_on_update,
            model=model,
        )
    except Exception:
        return ""


def is_admin() -> bool:
    """Проверка, является ли текущий пользователь администратором.

    В режиме разработки (IS_DEV_ADMIN=True) всегда возвращает True,
    чтобы упростить локальную работу.
    """

    if IS_DEV_ADMIN:
        return True
    if current_user and getattr(current_user, "role", "user") == "admin":
        return True
    return False


def _slugify(value: str) -> str:
    """Простая функция для генерации безопасного имени файла."""

    value = value.strip().lower().replace(" ", "_")
    allowed = "abcdefghijklmnopqrstuvwxyz0123456789_-"
    return "".join(ch for ch in value if ch in allowed)[:60] or "lesson_plan"



def _build_openrouter_headers(api_key: str) -> dict:
    return openrouter_client.build_headers(api_key)


def _markdown_to_html(markdown_text: str) -> str:
    """Конвертирует Markdown -> HTML для загрузки в Quill.

    Если пакет `markdown` недоступен, делаем безопасный HTML из plain text.
    """

    text = (markdown_text or "").replace("\r\n", "\n")
    try:
        import markdown as _md

        return _md.markdown(text)
    except Exception:
        escaped = html.escape(text)
        escaped = escaped.replace("\n\n", "</p><p>").replace("\n", "<br>")
        return f"<p>{escaped}</p>"



def _normalize_html_for_change_detection(html_text: str) -> str:
    """Нормализует HTML для сравнения.

    Quill часто держит хвостовой `<p><br></p>` как "место для курсора".
    Его игнорируем при сравнении, чтобы не перерисовывать редактор на каждый ввод.
    """

    s = (html_text or "").strip()
    # Срезаем хвостовые пустые параграфы
    s = re.sub(
        r"(?:<p>(?:\s|&nbsp;)*<br\s*/?>(?:\s|&nbsp;)*</p>\s*)+$",
        "",
        s,
        flags=re.IGNORECASE,
    )
    s = re.sub(r"(?:<p>(?:\s|&nbsp;)*</p>\s*)+$", "", s, flags=re.IGNORECASE)
    return s.strip()


def _sanitize_html_for_quill(html_text: str) -> str:
    return quill_html_utils.sanitize_html_for_quill(html_text)


def _normalize_lists_in_html(html_text: str) -> str:
    return quill_html_utils.normalize_lists_in_html(html_text)


def _replace_html_range_with_html(html_text: str, index: int, length: int, replacement_html: str) -> str:
    """Replace a plain-text range [index:index+length) in the HTML with an HTML fragment.

    This walks text nodes using BeautifulSoup, finds the nodes covering the requested
    plain-text character range and substitutes them with the provided HTML fragment.
    It's a best-effort approach designed to preserve surrounding tags and formatting.
    """
    if html_text is None:
        html_text = ""
    if not isinstance(html_text, str):
        html_text = str(html_text)

    soup = BeautifulSoup(html_text, "html.parser")
    container = soup.body if soup.body else soup

    # Collect all text nodes in document order with their start/end offsets
    text_nodes = []
    offset = 0
    for node in container.descendants:
        if isinstance(node, NavigableString):
            txt = str(node)
            if txt:
                start = offset
                end = offset + len(txt)
                text_nodes.append({"node": node, "start": start, "end": end, "text": txt})
                offset = end

    # If no text nodes, just append the replacement to the container
    if not text_nodes:
        try:
            frag = BeautifulSoup(replacement_html or "", "html.parser")
            container.append(frag)
            return str(soup)
        except Exception:
            return str(soup)

    range_start = max(0, int(index))
    range_end = min(offset, int(index + length))

    # Find start and end nodes
    start_info = None
    end_info = None
    for i, info in enumerate(text_nodes):
        if start_info is None and info["end"] > range_start:
            start_info = (i, info)
        if info["end"] >= range_end:
            end_info = (i, info)
            break

    if start_info is None or end_info is None:
        # Range outside text content; append replacement at end
        try:
            frag = BeautifulSoup(replacement_html or "", "html.parser")
            container.append(frag)
            return str(soup)
        except Exception:
            return str(soup)

    si, s_info = start_info
    ei, e_info = end_info

    s_node = s_info["node"]
    e_node = e_info["node"]
    s_txt = s_info["text"]
    e_txt = e_info["text"]

    s_off = range_start - s_info["start"]
    e_off = range_end - e_info["start"]

    # Build prefix/suffix
    prefix = s_txt[:s_off]
    suffix = e_txt[e_off:]

    # Replace across nodes:
    if s_node == e_node:
        # Simple case: single node
        try:
            new_frag = BeautifulSoup(replacement_html or "", "html.parser")
            # Replace text in the node with prefix + frag + suffix
            new_nodes = []
            if prefix:
                new_nodes.append(NavigableString(prefix))
            for child in new_frag.contents:
                new_nodes.append(child)
            if suffix:
                new_nodes.append(NavigableString(suffix))

            for new_n in reversed(new_nodes):
                e_node.insert_after(new_n)
            e_node.extract()
            return str(soup)
        except Exception:
            return str(soup)
    else:
        # Multi-node replacement
        try:
            # Trim start node to prefix
            s_node.replace_with(NavigableString(prefix))
            # Trim end node to suffix but we'll insert suffix later
            # Remove intermediate nodes between s_node and e_node
            cur = s_node.next_element
            nodes_to_remove = []
            while cur and cur is not e_node:
                next_cur = cur.next_element
                try:
                    if isinstance(cur, NavigableString):
                        nodes_to_remove.append(cur)
                    else:
                        # also remove empty elements which became irrelevant
                        pass
                except Exception:
                    pass
                cur = next_cur

            for n in nodes_to_remove:
                try:
                    n.extract()
                except Exception:
                    pass

            # Now replace e_node with suffix
            # Insert replacement fragment after the prefix node
            prefix_node = None
            # find the node that contains prefix (it was replaced by NavigableString(prefix))
            for node in container.descendants:
                if isinstance(node, NavigableString) and str(node) == prefix:
                    prefix_node = node
                    break

            frag = BeautifulSoup(replacement_html or "", "html.parser")
            insert_target = prefix_node if prefix_node is not None else container
            for child in frag.contents:
                insert_target.insert_after(child)
                insert_target = child

            # Insert suffix after the last inserted fragment
            if suffix:
                last_inserted = insert_target
                last_inserted.insert_after(NavigableString(suffix))

            # Finally remove the original end node
            try:
                e_node.extract()
            except Exception:
                pass

            return str(soup)
        except Exception:
            return str(soup)


def _build_lesson_plan_messages(*, subject: str, grade: str, topic: str, lesson_type: str, class_level: str, notes: str, extra_instructions: str = "") -> list:
    # Языковые особенности — добавляем инструкции, если предмет — белорусский или английский
    language_tail = ""
    subj_lower = (subject or "").lower()
    if "белоро" in subj_lower or "беларус" in subj_lower:
        language_tail = (
            "Ответ сформулируй на белорусском языке. Учитывай нормы белорусской орфографии и фонетики, "
            "включи упражнения на чтение, письмо и работу с текстом, варианты дифференцированных заданий. "
            "Адаслай на беларускай мове."
        )
    elif "иностранн" in subj_lower and "англ" in subj_lower or "английск" in subj_lower:
        language_tail = (
            "Respond in English. Focus on foreign-language teaching methods: communicative tasks, "
            "speaking/listening practice, controlled vocabulary activities, and level-appropriate (A1-A2) differentiation."
        )

    base_prompt = f"""
    СОЗДАЙ ДЕТАЛЬНЫЙ ПЛАН УРОКА ДЛЯ УЧИТЕЛЯ

    ПРЕДМЕТ: {subject}
    КЛАСС: {grade}
    УРОВЕНЬ ПОДГОТОВКИ КЛАССА: {class_level or 'средний'}
    ТИП УРОКА: {lesson_type}
    ТЕМА: {topic}
    ВРЕМЯ: 45 минут
    ДОПОЛНИТЕЛЬНО: {notes if notes else 'нет'}

    СТРУКТУРА (обязательно):
    1. Тема урока
    2. Цели урока (предметные, метапредметные, личностные)
    3. Планируемые результаты
    4. Оборудование и ресурсы
    5. Ход урока с точным таймингом:
       - Организационный момент (2-3 мин)
       - Актуализация знаний (5-7 мин)
       - Изучение нового материала (15-20 мин)
       - Закрепление (10-12 мин)
       - Рефлексия и домашнее задание (3-5 мин)
    6. Дифференцированное домашнее задание
    7. Приложения (материалы для урока)

    Формат: Markdown с заголовками ##
    Будь конкретен, практичен, учитывай ФГОС.
    ВКЛЮЧИ РАЗДЕЛЫ С ЗАДАНИЯМИ И АКТИВНОСТЯМИ:
    - Приведи 3 задания по уровням сложности (для слабого/среднего/сильного учащихся).
    - Подбери формы работы и типы упражнений, подходящие для указанного уровня подготовки класса.
    - Для смешанного класса предложи варианты дифференциации и адаптации для разноуровневых групп.
    """

    curriculum_tail = (
        f"Составь план в соответствии с учебной программой по {subject} для учреждений общего среднего образования "
        "Республики Беларусь (утверждённой Министерством образования Республики Беларусь)."
    )

    prompt = base_prompt + "\n\n" + curriculum_tail
    if language_tail:
        prompt = prompt + "\n\n" + language_tail
    if extra_instructions:
        prompt = prompt + "\n\nДополнительно: " + extra_instructions

    language_mode = None
    if "белоро" in subj_lower or "беларус" in subj_lower:
        language_mode = "be"
    elif "иностранн" in subj_lower and "англ" in subj_lower or "английск" in subj_lower:
        language_mode = "en"

    system_message = None
    if language_mode == "be":
        system_message = (
            "Адказвай па-беларуску. Улічвай нормы беларускай арфаграфіі і фанетыкі; "
            "давай практычныя заданні па чытанню, пісьму і працы з тэкстам; уключай дыферэнцыраваныя варыянты."
        )
    elif language_mode == "en":
        system_message = (
            "Respond in English. Focus on foreign-language teaching methods: communicative tasks, "
            "speaking/listening practice, controlled vocabulary activities, and level-appropriate differentiation."
        )

    messages = []
    if system_message:
        messages.append({"role": "system", "content": system_message})
    messages.append({"role": "user", "content": prompt})
    return messages


def _postprocess_plan_text(raw_text: str) -> str:
    import re

    if not raw_text:
        return ""

    # Базовая нормализация переносов
    text = (
        raw_text.replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\u200b", "")
        .replace("\xa0", "")
    ).strip("\n")

    # Разбиваем на строки
    lines = text.split("\n")

    # Убираем обёртку ```...```
    if lines and lines[0].lstrip().startswith("``"):
        for i in range(len(lines) - 1, 0, -1):
            if lines[i].strip() == "```":
                lines = lines[1:i]
                break

    # Убираем пустые пункты списков
    empty_list_item_re = re.compile(r"^\s*(([-*•])|(\d+\.))\s*$")
    lines = [ln for ln in lines if not empty_list_item_re.match(ln)]

    # Убираем общий левый отступ (если он большой)
    non_empty = [ln for ln in lines if ln.strip()]
    if non_empty:
        min_indent = min(len(ln) - len(ln.lstrip(" ")) for ln in non_empty)
        if min_indent >= 4:
            lines = [ln[min_indent:] if len(ln) >= min_indent else ln for ln in lines]

    # Функция проверки, является ли строка элементом списка
    def is_list_item(s: str) -> bool:
        s = s.strip()
        return (
            s.startswith(("-", "*", "•"))
            or re.match(r"^\d+\.", s) is not None
        )

    # 🔥 Основная очистка пустых строк
    cleaned = []
    prev_empty = False

    for i, ln in enumerate(lines):
        stripped = ln.strip()

        # Пустая строка
        if stripped == "":
            # Удаляем пустую строку между элементами списка
            if i > 0 and i < len(lines) - 1:
                if is_list_item(lines[i - 1]) and is_list_item(lines[i + 1]):
                    continue

            # Удаляем пустую строку сразу после заголовков
            if cleaned and cleaned[-1].strip().startswith(("#", "##", "###", "####")):
                continue

            # Обычная логика: не даём двум пустым подряд
            if not prev_empty:
                cleaned.append("")
            prev_empty = True
            continue

        # Непустая строка
        cleaned.append(ln)
        prev_empty = False

    # Убираем пустые строки в начале и конце
    while cleaned and cleaned[0].strip() == "":
        cleaned.pop(0)
    while cleaned and cleaned[-1].strip() == "":
        cleaned.pop()

    return "\n".join(cleaned)


def _normalize_docx_filename(title: str) -> str:
    safe = re.sub(r"[^0-9A-Za-zА-Яа-яЁё_\- ]+", "", (title or "")).strip()
    safe = safe[:80] if safe else "lesson_plan"
    return f"{_slugify(safe)}.docx"


def _html_to_docx_bytes(html: str) -> bytes:
    from docx import Document

    def add_inline(paragraph, node, *, bold=False, italic=False):
        if isinstance(node, NavigableString):
            text = str(node)
            if text:
                run = paragraph.add_run(text)
                run.bold = bold
                run.italic = italic
            return

        if not hasattr(node, "name"):
            return

        name = (node.name or "").lower()
        if name in {"strong", "b"}:
            for child in node.children:
                add_inline(paragraph, child, bold=True or bold, italic=italic)
            return
        if name in {"em", "i"}:
            for child in node.children:
                add_inline(paragraph, child, bold=bold, italic=True or italic)
            return
        if name == "br":
            paragraph.add_run("\n")
            return

        # span/a/etc — просто рекурсивно обходим
        for child in node.children:
            add_inline(paragraph, child, bold=bold, italic=italic)

    soup = BeautifulSoup((html or ""), "html.parser")
    doc = Document()

    body = soup.body if soup.body else soup

    def add_block(tag):
        name = (tag.name or "").lower()
        if name in {"h1", "h2", "h3", "h4"}:
            level = {"h1": 1, "h2": 2, "h3": 3, "h4": 4}[name]
            text = tag.get_text(" ", strip=True)
            if text:
                doc.add_heading(text, level=level)
            return
        if name in {"p", "div"}:
            # Quill часто отдаёт <p><br></p>
            if not tag.get_text(strip=True) and not tag.find(["strong", "em", "b", "i"]):
                doc.add_paragraph("")
                return
            p = doc.add_paragraph("")
            for child in tag.children:
                add_inline(p, child)
            return
        if name in {"ul", "ol"}:
            style = "List Bullet" if name == "ul" else "List Number"
            for li in tag.find_all("li", recursive=False):
                p = doc.add_paragraph("", style=style)
                for child in li.children:
                    # поддержка вложенных списков
                    if getattr(child, "name", None) and child.name.lower() in {"ul", "ol"}:
                        add_block(child)
                    else:
                        add_inline(p, child)
            return

        # неизвестный блок — пытаемся обработать детей
        for child in tag.children:
            if getattr(child, "name", None):
                add_block(child)

    for child in body.children:
        if getattr(child, "name", None):
            add_block(child)

    buff = BytesIO()
    doc.save(buff)
    return buff.getvalue()


st.header("Генерация плана урока (ИИ)")

# Разделяем экран: левая колонка — форма генерации, правая — редактор результата
col_form, col_editor = st.columns([2, 3])

with col_form:
    grade = st.selectbox("Класс", GRADES, index=3, key="gen_grade")
    subject = st.selectbox("Предмет", SUBJECTS, index=0, key="gen_subject")
    topic = st.text_input("Тема урока", placeholder="Десятичные дроби", help="Ключевая тема занятия", key="gen_topic")
    # Тип урока — выбирает учитель
    lesson_type = st.selectbox(
        "Тип урока",
        [
            "объяснение нового материала",
            "комбинированный",
            "закрепление",
            "повторение",
            "контрольный",
            "практическая работа / лабораторная",
        ],
        index=1,
    )
    class_level = st.selectbox(
        "Уровень подготовки класса",
        ["слабый", "средний", "сильный", "смешанный"],
        index=1,
        key="gen_class_level",
    )
    notes = st.text_area("Особенности класса / пожелания", placeholder="Уровень класса, акценты, что важно подчеркнуть...")
    # (Упрощено) шаблон промпта можно править вручную внизу — кнопка автозагрузки убрана

    # Редактируемый шаблон промпта (можно подправить перед генерацией)
    if "prompt_template" not in st.session_state:
        st.session_state["prompt_template"] = ""
    with st.expander("Шаблон промпта (можно править)"):
        st.text_area("Шаблон промпта", key="prompt_template", height=200)
    model_choice = st.selectbox(
        "Источник генерации",
        [
            "Локальный шаблон (без API)",
            "Deepseek API (через ключ)",
        ],
        index=1,
    )
    visibility = st.selectbox("Видимость плана", ["public", "private", "pending"], index=0)

    # Подсказки тем из существующих материалов и планов для выбранного предмета и класса
    existing_plans = list_lesson_plans(limit=300)
    existing_materials = list_materials(limit=300)

    topic_candidates = set()
    for p in existing_plans:
        if p.subject == subject and p.grade == grade and p.topic:
            topic_candidates.add(p.topic)
    for m in existing_materials:
        if getattr(m, "subject", None) == subject and getattr(m, "grade", None) == grade and m.topics:
            for t in m.topics.split(","):
                t = t.strip()
                if t:
                    topic_candidates.add(t)

    # Подсадим темы из календарно-тематического планирования (KTP)
    try:
        ktp_topics = get_calendar_topics_for_subject(subject)
        for t in ktp_topics:
            topic_candidates.add(t)
    except Exception:
        pass

    typed = st.session_state.get("gen_topic", "") or ""
    if typed:
        # Общие совпадения из материалов и планов
        matches = [t for t in topic_candidates if typed.lower() in t.lower()]
        matches = sorted(matches)[:10]
        if matches:
            st.caption("Возможные темы из планов/материалов:")
            for i, t in enumerate(matches):
                if st.button(t, key=f"suggest_topic_{i}"):
                    st.session_state["gen_topic"] = t
                    safe_rerun()

        # Подсказки конкретно из календарно-тематического планирования (KTP)
        try:
            ktp_topics = get_calendar_topics_for_subject(subject)
        except Exception:
            ktp_topics = []

        ktp_matches = [t for t in ktp_topics if typed.lower() in t.lower()]
        ktp_matches = sorted(ktp_matches)[:10]
        if ktp_matches:
            st.caption("Подсказки из KTP:")
            for i, t in enumerate(ktp_matches):
                if st.button(f"{t} — из KTP", key=f"ktp_suggest_{i}"):
                    st.session_state["gen_topic"] = t
                    st.success("Тема взята из календарно‑тематического планирования.")
                    safe_rerun()

    generate_clicked = st.button("Сгенерировать план урока")

    if generate_clicked:
        if not subject or not topic:
            st.warning("Укажите хотя бы предмет и тему урока.")
        elif model_choice == "Deepseek API (через ключ)" and api_key:
            headers = _build_openrouter_headers(api_key)
            messages = _build_lesson_plan_messages(
                subject=subject,
                grade=grade,
                topic=topic,
                lesson_type=lesson_type,
                class_level=class_level,
                notes=notes,
                extra_instructions=st.session_state.get("prompt_template", ""),
            )

            st.session_state["is_generating"] = True
            st.session_state["start_stream_now"] = True
            st.session_state["stream_buffer"] = ""
            st.session_state["generated_headers"] = headers
            st.session_state["generated_messages"] = messages
            st.session_state["generated_model"] = "deepseek/deepseek-chat"
            st.session_state["generated_title"] = f"{subject or 'Урок'} — {topic}"[:200]
        else:
            plan_text = generate_lesson_plan_locally(subject, grade, topic, notes, class_level)
            st.session_state["editor_title"] = f"{subject or 'Урок'} — {topic}"[:200]
            # Локальная генерация возвращает Markdown — прогоняем через normalize -> markdown_to_html
            md = normalize_ai_markdown(_postprocess_plan_text(plan_text))
            st.session_state["editor_html"] = markdown_to_html(md)
            st.session_state["editor_instance"] = st.session_state.get("editor_instance", 0) + 1
            st.success("✅ План сгенерирован и загружен в редактор справа. Отредактируйте текст и нажмите 'Сохранить в БД'.")

with col_editor:
    st.subheader("Редактор плана урока")

    # Оставляем только визуальный редактор (WYSIWYG), чтобы не отвлекать учителя Markdown-разметкой.

    stream_placeholder = st.empty()

    # Если идёт генерация — показываем потоковый предпросмотр.
    # ВАЖНО: после окончания стрима сразу переключаемся на Quill в этом же прогоне,
    # без safe_rerun (иначе можно "застрять" без редактора).
    if st.session_state.get("is_generating"):
        if st.session_state.get("start_stream_now"):
            st.session_state["start_stream_now"] = False
            messages = st.session_state.pop("generated_messages", None)
            headers = st.session_state.pop("generated_headers", None)
            model_to_use = st.session_state.pop("generated_model", "deepseek/deepseek-chat")

            full_text = ""
            try:
                if messages and headers:
                    with st.spinner("🤖 Генерирую..."):
                        full_text = stream_generate_chat_via_api(
                            messages=messages,
                            headers=headers,
                            placeholder=stream_placeholder,
                            model=model_to_use,
                        )
            except Exception:
                full_text = ""

            if not full_text:
                full_text = generate_lesson_plan_locally(subject, grade, topic, notes, class_level)

            st.session_state["stream_buffer"] = full_text
            # Сохраняем сгенерированный Markdown отдельно — НЕ загружаем автоматически в редактор.
            st.session_state["generated_content"] = full_text
            st.session_state["is_generating"] = False

        stream_buffer = st.session_state.get("stream_buffer", "")
        if stream_buffer:
            stream_placeholder.markdown(_postprocess_plan_text(stream_buffer))

    if not st.session_state.get("is_generating"):
        # Если есть сгенерированный план (из предыдущего запуска), переместим его в editor_* перед созданием виджетов
        # Не загружаем автоматически `generated_content` — используем кнопку загрузки ниже.
        if "generated_title" in st.session_state:
            st.session_state["editor_title"] = st.session_state.pop("generated_title")

        # Инициализация содержимого редактора в session_state по умолчанию (делается один раз)
        if "editor_html" not in st.session_state:
            st.session_state.editor_html = ""
            st.session_state.editor_instance = 0
        if "editor_title" not in st.session_state:
            st.session_state["editor_title"] = ""

        # Поле заголовка и сам редактор (WYSIWYG)
        st.text_input("Заголовок плана", key="editor_title")

        # Кнопка: единственное место, где загружаем Markdown от ИИ в редактор (normalize -> markdown_to_html -> load)
        if st.button("Загрузить текст от ИИ"):
            ai_md = st.session_state.get("generated_content") or st.session_state.get("stream_buffer") or ""
            if ai_md:
                # Сначала прогоняем через postprocess, чтобы убрать обёртки, кодовые блоки
                # и нормализовать отступы — это позволяет markdown->HTML правильно
                # превращать заголовки (##, ###) в теги <h2>/<h3>.
                ai_md = _postprocess_plan_text(ai_md)
                md = normalize_ai_markdown(ai_md)
                html_val = markdown_to_html(md)
                # Сантехника: привести HTML к компактному виду, чтобы Quill не добавлял
                # лишние пустые параграфы между блоками.
                html_val = _sanitize_html_for_quill(html_val)
                st.session_state.editor_html = html_val
                st.session_state.editor_instance = st.session_state.get("editor_instance", 0) + 1
            else:
                st.warning("Нет сгенерированного текста для загрузки.")

        # --- Визуальный редактор: предпочитаем наш Quill-компонент (даёт события выделения по ПКМ)
        if "quill_pending_replace" not in st.session_state:
            st.session_state["quill_pending_replace"] = None
        if "quill_apply_replace" not in st.session_state:
            st.session_state["quill_apply_replace"] = None
        if "quill_apply_replace_sent" not in st.session_state:
            st.session_state["quill_apply_replace_sent"] = False
        if "quill_apply_pending_id" not in st.session_state:
            st.session_state["quill_apply_pending_id"] = None

        instr_key = "quill_ai_replace_instr"
        if instr_key not in st.session_state:
            st.session_state[instr_key] = "Перепиши текст, сохрани смысл, улучшив ясность и сократив длину."
        auto_key = "quill_ai_replace_auto"
        if auto_key not in st.session_state:
            st.session_state[auto_key] = True

        with st.expander("Настройки AI-замены выделения", expanded=False):
            st.checkbox("Автоматически заменять после ПКМ", key=auto_key)
            st.text_input("Инструкция для ИИ", key=instr_key)

        # Если в прошлый прогон мы уже отправили applyReplace во фронт, то сейчас очищаем,
        # чтобы замена не применялась повторно.
        if st.session_state.get("quill_apply_replace_sent") and st.session_state.get("quill_apply_replace") is not None:
            st.session_state["quill_apply_replace"] = None
            st.session_state["quill_apply_replace_sent"] = False

        # UI для подтверждения AI-замены после ПКМ
        pending = st.session_state.get("quill_pending_replace")
        if pending and isinstance(pending, dict):
            with st.container(border=True):
                st.subheader("ИИ-замена выделения")
                st.caption("В редакторе выделите текст → ПКМ → 'Заменить на другой вариант (AI)'.")
                st.text_area("Выделенный фрагмент", value=pending.get("text", ""), height=120, disabled=True)
                st.text_input("Инструкция для ИИ", key=instr_key)
                c1, c2 = st.columns([1, 1])
                if c1.button("Сгенерировать и заменить", key="quill_ai_replace_apply"):
                    api_key = st.session_state.get("api_key") or os.getenv("OPENROUTER_API_KEY")
                    if not api_key:
                        st.error("API ключ не найден. Укажите OpenRouter API key слева (sk-or-v1-...).")
                    else:
                        sel_text = (pending.get("text") or "").strip()
                        if not sel_text:
                            st.warning("Пустое выделение.")
                        elif len(sel_text) > 4000:
                            st.error("Фрагмент слишком длинный (макс 4000 символов). Разбейте на части.")
                        else:
                            prompt = (
                                "Заменить фрагмент текста.\n"
                                "Ответ дайте только новым текстом без дополнительного комментария.\n\n"
                                f"Фрагмент:\n---\n{sel_text}\n---\n"
                                f"Инструкция: {st.session_state[instr_key]}"
                            )
                            with st.spinner("Отправляю запрос к ИИ..."):
                                resp = generate_with_deepseek(api_key, prompt)
                            ai_text = None
                            if isinstance(resp, dict):
                                ai_text = resp.get("choices", [{}])[0].get("message", {}).get("content")
                            ai_text = (ai_text or "").strip()
                            if not ai_text:
                                st.error("Не удалось получить ответ от ИИ.")
                            else:
                                st.session_state["quill_apply_replace"] = {
                                    "id": int(pending.get("id") or 0),
                                    "range": pending.get("range") or {"index": 0, "length": 0},
                                    "text": ai_text,
                                }
                                st.session_state["quill_pending_replace"] = None
                                hist = st.session_state.get("ai_edit_history", [])
                                hist.insert(
                                    0,
                                    {
                                        "time": datetime.utcnow().isoformat(),
                                        "sel": sel_text,
                                        "instr": st.session_state[instr_key],
                                        "result": ai_text,
                                    },
                                )
                                st.session_state["ai_edit_history"] = hist[:20]
                                safe_rerun()

                if c2.button("Отмена", key="quill_ai_replace_cancel"):
                    st.session_state["quill_pending_replace"] = None
                    safe_rerun()

        if quill_editor is not None and not st.session_state.get("quill_component_failed"):
            apply_replace_arg = None
            if st.session_state.get("quill_apply_replace") is not None and not st.session_state.get("quill_apply_replace_sent"):
                apply_replace_arg = st.session_state.get("quill_apply_replace")

            evt = quill_editor(
                value=st.session_state.editor_html,
                height=420,
                placeholder="Введите текст...",
                apply_replace=apply_replace_arg,
                key=f"editor_{st.session_state['editor_instance']}",
            )

            # Если компонент не загрузился в браузере, Streamlit часто возвращает None.
            # В этом случае сразу переключаемся на fallback-редактор, чтобы приложение
            # оставалось рабочим (вместо "Your app is having trouble loading...").
            if evt is None:
                st.session_state["quill_component_failed"] = True
                svr_log = st.session_state.get("quill_server_log", [])
                svr_log.insert(0, {"time": datetime.utcnow().isoformat(), "event": "component_failed_load"})
                st.session_state["quill_server_log"] = svr_log[:50]
                st.warning("Quill-компонент не загрузился — использую fallback (streamlit-quill).")
                if st_quill is None:
                    st.error("Визуальный редактор недоступен: пакет streamlit-quill не установлен.")
                    st.stop()

                html_value = st_quill(
                    value=st.session_state.editor_html,
                    html=True,
                    key=f"editor_fallback_{st.session_state['editor_instance']}",
                )
                if html_value is not None:
                    st.session_state.editor_html = html_value
                evt = {"type": "content", "html": st.session_state.editor_html}

            # Помечаем, что payload отправлен во фронт (ровно один раз)
            # Флаг отправки будем устанавливать только после получения контентного события
            # из фронтенда, чтобы избежать гонки и преждевременного сброса состояний.
            if apply_replace_arg is not None:
                svr_log = st.session_state.get("quill_server_log", [])
                svr_log.insert(0, {"time": datetime.utcnow().isoformat(), "event": "apply_sent", "id": apply_replace_arg.get("id") if isinstance(apply_replace_arg, dict) else None})
                st.session_state["quill_server_log"] = svr_log[:50]
                # Сохраним id ожидаемой замены, чтобы при получении следующего content
                # понимать, что это твой применённый результат.
                st.session_state["quill_apply_pending_id"] = apply_replace_arg.get("id") if isinstance(apply_replace_arg, dict) else None

            # Обработка событий из редактора
            if isinstance(evt, dict):
                # Успешный ответ — сбрасываем null-счётчик
                st.session_state["quill_null_cnt"] = 0
                if evt.get("type") == "content":
                    html_value = evt.get("html")
                    if html_value is not None:
                        st.session_state.editor_html = html_value
                        svr_log = st.session_state.get("quill_server_log", [])
                        svr_log.insert(0, {"time": datetime.utcnow().isoformat(), "event": "content_received", "html_len": len(html_value)})
                        st.session_state["quill_server_log"] = svr_log[:50]
                        # Если была ожидаемая замена — отмечаем её как применённую и очищаем флаги
                        pending_id = st.session_state.get("quill_apply_pending_id")
                        if pending_id is not None:
                            # Отмечаем, что замена применена и очищаем все соответствующие флаги
                            st.session_state["quill_apply_replace_sent"] = False
                            st.session_state["quill_apply_replace"] = None
                            st.session_state["quill_apply_pending_id"] = None
                            svr_log.insert(0, {"time": datetime.utcnow().isoformat(), "event": "apply_applied", "id": pending_id})
                            st.session_state["quill_server_log"] = svr_log[:50]
                elif evt.get("type") == "debug":
                    # Логируем отладочные сообщения от фронтенда компонента
                    dbg = st.session_state.get("quill_debug_log", [])
                    try:
                        msg = evt.get("msg") or "debug"
                        data = evt.get("data") or {}
                        dbg.insert(0, {"time": datetime.utcnow().isoformat(), "msg": msg, "data": data})
                        st.session_state["quill_debug_log"] = dbg[:50]
                    except Exception:
                        pass
                elif evt.get("type") == "apply_ack":
                    # Фронтенд подтвердил, что применил замену — считаем задачу выполненной.
                    try:
                        ack_id = evt.get("id")
                        svr_log = st.session_state.get("quill_server_log", [])
                        svr_log.insert(0, {"time": datetime.utcnow().isoformat(), "event": "apply_ack_received", "id": ack_id})
                        st.session_state["quill_server_log"] = svr_log[:50]
                        # Отметим, что замена применена и очистим ожидающие поля
                        st.session_state["quill_apply_replace"] = None
                        st.session_state["quill_apply_replace_sent"] = True
                        st.session_state["quill_apply_pending_id"] = None
                        # Попробуем аккуратно перерисовать интерфейс, если серверная попытка не выполнилась
                        try:
                            svr_log.insert(0, {"time": datetime.utcnow().isoformat(), "event": "apply_ack_triggers_rerun", "id": ack_id})
                            st.session_state["quill_server_log"] = svr_log[:50]
                            safe_rerun()
                        except Exception:
                            svr_log.insert(0, {"time": datetime.utcnow().isoformat(), "event": "apply_ack_rerun_failed", "id": ack_id})
                            st.session_state["quill_server_log"] = svr_log[:50]
                    except Exception:
                        pass
                elif evt.get("type") == "replace_request":
                    req = {
                        "id": evt.get("id"),
                        "range": evt.get("range"),
                        "text": evt.get("text"),
                    }

                    # По умолчанию делаем замену в 1 клик (после ПКМ).
                    sel_text = (req.get("text") or "").strip()
                    api_key = st.session_state.get("api_key") or os.getenv("OPENROUTER_API_KEY")
                    can_auto = bool(st.session_state.get(auto_key)) and bool(api_key) and bool(sel_text) and len(sel_text) <= 4000

                    if can_auto:
                        prompt = (
                            "Заменить фрагмент текста.\n"
                            "Ответ дайте только новым текстом без дополнительного комментария.\n\n"
                            f"Фрагмент:\n---\n{sel_text}\n---\n"
                            f"Инструкция: {st.session_state[instr_key]}"
                        )
                        with st.spinner("Заменяю выделение через ИИ..."):
                            resp = generate_with_deepseek(api_key, prompt)
                        ai_text = None
                        if isinstance(resp, dict):
                            ai_text = resp.get("choices", [{}])[0].get("message", {}).get("content")
                        ai_text = (ai_text or "").strip()
                        if not ai_text:
                            # Переходим в ручной режим
                            st.session_state["quill_pending_replace"] = req
                            safe_rerun()
                        else:
                            # Автоматически применяем замену сразу, без повторного ПКМ
                            payload = {
                                "id": int(req.get("id") or 0),
                                "range": req.get("range") or {"index": 0, "length": 0},
                                "text": ai_text,
                            }
                            # Попробуем применить замену серверно, чтобы не зависеть от race-флагов
                            try:
                                repl_html = _markdown_to_html(ai_text)
                                new_html = _replace_html_range_with_html(
                                    st.session_state.get("editor_html", ""),
                                    int(payload["range"].get("index", 0)),
                                    int(payload["range"].get("length", 0)),
                                    repl_html,
                                )
                                # Сантехника: прогоняем нормализацию
                                new_html = _sanitize_html_for_quill(new_html)
                                new_html = _normalize_lists_in_html(new_html)

                                st.session_state["editor_html"] = new_html
                                # Логируем и сохраняем в историю
                                hist = st.session_state.get("ai_edit_history", [])
                                hist.insert(
                                    0,
                                    {
                                        "time": datetime.utcnow().isoformat(),
                                        "sel": sel_text,
                                        "instr": st.session_state[instr_key],
                                        "result": ai_text,
                                    },
                                )
                                st.session_state["ai_edit_history"] = hist[:20]

                                svr_log = st.session_state.get("quill_server_log", [])
                                svr_log.insert(0, {"time": datetime.utcnow().isoformat(), "event": "apply_server_applied", "id": payload["id"]})
                                st.session_state["quill_server_log"] = svr_log[:50]

                                # Очистим вспомогательные поля (замена применена сразу)
                                st.session_state["quill_pending_replace"] = None
                                st.session_state["quill_apply_last_payload"] = None
                                st.session_state["quill_apply_pending_id"] = None
                                st.session_state["quill_apply_queued_at"] = None
                                st.session_state["quill_apply_retry_count"] = 0

                                # Попробуем аккуратно перерисовать интерфейс, чтобы клиент увидел
                                # обновлённый HTML сразу. Увеличиваем счётчик инстанса редактора,
                                # чтобы компонент пересоздался и пропатчил новое содержимое.
                                try:
                                    st.session_state["editor_instance"] = st.session_state.get("editor_instance", 0) + 1
                                except Exception:
                                    pass

                                # Покажем пользователю краткое уведомление в интерфейсе
                                try:
                                    st.success("ИИ: замена применена")
                                except Exception:
                                    pass

                                # Инициируем безопасный rerun, чтобы Streamlit отправил новый
                                # state во фронтенд. Это может слегка перерисовать UI, но
                                # гарантирует, что редактор получит новое содержимое.
                                try:
                                    svr_log = st.session_state.get("quill_server_log", [])
                                    svr_log.insert(0, {"time": datetime.utcnow().isoformat(), "event": "apply_server_rerun_attempt", "id": payload["id"]})
                                    st.session_state["quill_server_log"] = svr_log[:50]
                                    safe_rerun()
                                except Exception:
                                    svr_log = st.session_state.get("quill_server_log", [])
                                    svr_log.insert(0, {"time": datetime.utcnow().isoformat(), "event": "apply_server_rerun_failed", "id": payload["id"]})
                                    st.session_state["quill_server_log"] = svr_log[:50]

                                st.session_state["quill_apply_server_applied"] = payload["id"]
                            except Exception as e:
                                # Если серверная вставка провалилась, откатываемся к старой модели (frontend apply)
                                svr_log = st.session_state.get("quill_server_log", [])
                                svr_log.insert(0, {"time": datetime.utcnow().isoformat(), "event": "apply_server_error", "error": str(e)})
                                st.session_state["quill_server_log"] = svr_log[:50]
                                # Фолбек: отправим payload во фронтенд как прежде
                                st.session_state["quill_apply_replace"] = payload
                                st.session_state["quill_apply_last_payload"] = payload
                                st.session_state["quill_apply_pending_id"] = payload["id"]
                                st.session_state["quill_apply_queued_at"] = time.time()
                                st.session_state["quill_apply_retry_count"] = 0
                                st.session_state["quill_apply_replace_sent"] = False
                                safe_rerun()
                            hist.insert(
                                0,
                                {
                                    "time": datetime.utcnow().isoformat(),
                                    "sel": sel_text,
                                    "instr": st.session_state[instr_key],
                                    "result": ai_text,
                                },
                            )
                            st.session_state["ai_edit_history"] = hist[:20]
                            safe_rerun()
                            # Логируем событие: поставили задачу на применение замены
                            svr_log = st.session_state.get("quill_server_log", [])
                            svr_log.insert(0, {"time": datetime.utcnow().isoformat(), "event": "apply_queued", "id": int(req.get("id") or 0)})
                            st.session_state["quill_server_log"] = svr_log[:50]
                    else:
                        # Нет ключа/слишком длинно/отключен авто-режим — покажем панель подтверждения.
                        st.session_state["quill_pending_replace"] = req
                        safe_rerun()
            else:
                # Если компонент вернул None или что-то неожиданное — считаем, что фронтенд не загрузился.
                # Переключение на fallback делаем выше (evt is None). Здесь оставляем счётчик
                # на случай редких нестабильностей.
                cnt = st.session_state.get("quill_null_cnt", 0) + 1
                st.session_state["quill_null_cnt"] = cnt
                if cnt >= 3:
                    st.session_state["quill_component_failed"] = True
                    svr_log = st.session_state.get("quill_server_log", [])
                    svr_log.insert(0, {"time": datetime.utcnow().isoformat(), "event": "component_unresponsive"})
                    st.session_state["quill_server_log"] = svr_log[:50]
                    st.warning("Quill-компонент не отвечает — использую fallback (streamlit-quill).")
                    safe_rerun()
        else:
            # Fallback: старый streamlit-quill (без выделения/ПКМ событий)
            if st_quill is None:
                st.error("Визуальный редактор недоступен: пакет streamlit-quill не установлен.")
                st.stop()

            html_value = st_quill(
                value=st.session_state.editor_html,
                html=True,
                key=f"editor_{st.session_state['editor_instance']}",
            )
            if html_value is not None:
                st.session_state.editor_html = html_value

        # Отладка: показать реальный HTML, который сейчас в редакторе
        with st.expander("HTML (что реально в редакторе)"):
            st.code(st.session_state.editor_html, language="html")

        # Отладка: логи компонента Quill
        dbg_logs = st.session_state.get("quill_debug_log", [])
        with st.expander("Quill component debug (последние сообщения)"):
            if dbg_logs:
                for i, d in enumerate(dbg_logs[:20]):
                    ts = d.get("time")
                    msg = d.get("msg")
                    data = d.get("data")
                    st.markdown(f"**{i+1}. {msg}** — {ts}")
                    st.json(data)
            else:
                st.write("Пока нет debug-сообщений от компонента.")

        # Watchdog: перепроверим, не нужно ли повторно отправить applyReplace
        pending_id = st.session_state.get("quill_apply_pending_id")
        if pending_id is not None:
            queued_at = st.session_state.get("quill_apply_queued_at") or 0
            retry = st.session_state.get("quill_apply_retry_count", 0)
            last_payload = st.session_state.get("quill_apply_last_payload")
            elapsed = time.time() - (queued_at or 0)
            # Ждём небольшую задержку (1s) — если ACK/контент не пришёл, пробуем ещё до 3 раз.
            if last_payload and retry < 3 and elapsed > 1.0:
                st.session_state["quill_apply_replace"] = last_payload
                st.session_state["quill_apply_queued_at"] = time.time()
                st.session_state["quill_apply_retry_count"] = retry + 1
                svr_log = st.session_state.get("quill_server_log", [])
                svr_log.insert(0, {"time": datetime.utcnow().isoformat(), "event": "apply_retry", "id": pending_id, "attempt": retry + 1})
                st.session_state["quill_server_log"] = svr_log[:50]
                safe_rerun()
            elif retry >= 3 and elapsed > 1.0:
                # Даем пользователю ручной контроль: показываем панель подтверждения.
                st.session_state["quill_pending_replace"] = {"id": pending_id, "text": last_payload.get("text") if last_payload else "", "range": last_payload.get("range") if last_payload else {"index": 0, "length": 0}}
                # Очистим все вспомогательные поля
                st.session_state["quill_apply_last_payload"] = None
                st.session_state["quill_apply_pending_id"] = None
                st.session_state["quill_apply_queued_at"] = None
                st.session_state["quill_apply_retry_count"] = 0
                svr_log = st.session_state.get("quill_server_log", [])
                svr_log.insert(0, {"time": datetime.utcnow().isoformat(), "event": "apply_failed_giveup", "id": pending_id})
                st.session_state["quill_server_log"] = svr_log[:50]
                safe_rerun()

        # Отладка: серверные события для процесса applyReplace
        svr_logs = st.session_state.get("quill_server_log", [])
        with st.expander("Quill server events (последние)"):
            if svr_logs:
                for i, s in enumerate(svr_logs[:20]):
                    st.markdown(f"**{i+1}. {s.get('event')}** — {s.get('time')}")
                    st.json({k: v for k, v in s.items() if k not in ['time']})
            else:
                st.write("Пока нет серверных событий для Quill.")

        # Действия: сохранить, скачать .docx, очистить
        action_cols = st.columns([1, 1, 1])
        if action_cols[0].button("Сохранить в БД"):
            title = st.session_state.get("editor_title") or (st.session_state.get("gen_topic") or "План урока")
            try:
                content_to_save = st.session_state.get("editor_html", "")
                plan = create_lesson_plan(
                    title=title,
                    subject=subject,
                    grade=grade,
                    topic=topic,
                    class_level=class_level,
                    content=content_to_save,
                    model_name=("local-template" if model_choice.startswith("Локальный") else "deepseek"),
                    visibility=visibility,
                    author_id=(getattr(current_user, "id", None) if current_user else None),
                )
                st.success(f"План сохранён (id={plan.id})")
            except Exception as e:
                st.error(f"Ошибка сохранения: {e}")

        docx_title = st.session_state.get("editor_title") or (st.session_state.get("gen_topic") or "lesson_plan")
        html_for_docx = st.session_state.get("editor_html", "")
        docx_bytes = _html_to_docx_bytes(html_for_docx)
        action_cols[1].download_button(
            label="Скачать .docx",
            data=docx_bytes,
            file_name=_normalize_docx_filename(docx_title),
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )

        if action_cols[2].button("Очистить"):
            st.session_state["editor_html"] = ""
            st.session_state["editor_title"] = ""
            st.session_state["editor_instance"] = st.session_state.get("editor_instance", 0) + 1
            safe_rerun()

        # Примечание: раньше тут был режим «вставьте выделенный текст». Теперь основная замена
        # делается прямо в редакторе через ПКМ (см. блок выше).
if show_recent_plans:
    with st.expander("Последние сохранённые планы уроков", expanded=False):
        plans = list_lesson_plans(limit=10)
        if plans:
            for plan in plans:
                meta = f"{plan.subject or 'Без предмета'} — {plan.grade or 'Без класса'}"
                if getattr(plan, "class_level", None):
                    meta += f" | уровень: {plan.class_level}"
                created = plan.created_at.strftime("%d.%m.%Y %H:%M") if plan.created_at else ""
                st.markdown(f"**{plan.title}**  ")
                st.caption(f"{meta} | создан: {created} | источник: {plan.model_name or 'не указан'}")
                with st.expander("Показать план"):
                    content = plan.content or ""
                    looks_like_html = content.lstrip().startswith("<")
                    if looks_like_html:
                        st.markdown(content, unsafe_allow_html=True)
                    else:
                        st.markdown(content)

                    download_ext = "html" if looks_like_html else "md"
                    download_mime = "text/html" if looks_like_html else "text/markdown"
                    st.download_button(
                        label=f"Скачать как .{download_ext}",
                        data=content,
                        file_name=f"{_slugify(plan.title)}.{download_ext}",
                        mime=download_mime,
                        key=f"download_{plan.id}",
                    )
        else:
            st.info("Пока нет сохранённых планов. Сгенерируйте первый план слева.")

if app_mode == "Пользовательский режим":
    st.header("Рабочее пространство учителя")

    tab_concept, tab_handout, tab_quiz = st.tabs(["Конспект", "Раздаточный материал", "Викторина"])

    # ----- Вкладка: Конспект (текущая работа с планом) -----
    with tab_concept:
        st.subheader("Конспект: генерация и редактор")
        st.markdown("Используйте форму слева для генерации плана урока и редактор справа для правок.")
        # Показываем быстрый список последних конспектов
        with st.expander("Последние конспекты (файлы .docx)"):
            docs = sorted(materials_dir.glob("*.docx"))[:10]
            if docs:
                for p in docs:
                    st.write(p.name)
            else:
                st.write("Пока нет загруженных конспектов.")

    # ----- Вкладка: Раздаточный материал -----
    with tab_handout:
        st.subheader("Создать раздаточный материал")
        st.markdown("Тема автоматически подставляется из поля 'Тема урока' слева, если оно заполнено.")

        handout_subject = st.selectbox("Предмет", SUBJECTS, index=SUBJECTS.index(st.session_state.get('gen_subject', SUBJECTS[0])) if st.session_state.get('gen_subject') in SUBJECTS else 0)
        handout_grade = st.selectbox("Класс", GRADES, index=GRADES.index(st.session_state.get('gen_grade', GRADES[0])) if st.session_state.get('gen_grade') in GRADES else 0)
        handout_topic = st.text_input("Тема раздаточного материала", value=st.session_state.get("gen_topic", ""))
        handout_notes = st.text_area("Примечания (опционально)")

        st.markdown("---")
        st.markdown("Если у вас уже есть сгенерированный план в редакторе, вы можете создать раздаточный файл (.docx) из текущего содержимого:")

        col1, col2 = st.columns([1, 1])
        docx_title = _normalize_docx_filename(handout_topic or st.session_state.get("editor_title", "lesson_plan"))
        if col1.button("Создать раздаточный материал из текущего плана"):
            html_for_docx = st.session_state.get("editor_html", "")
            if not html_for_docx:
                st.warning("Нет содержимого в редакторе. Сгенерируйте или загрузите текст из ИИ сначала.")
            else:
                try:
                    bytes_docx = _html_to_docx_bytes(html_for_docx)
                    save_path = materials_dir / docx_title
                    with open(save_path, "wb") as fh:
                        fh.write(bytes_docx)

                    from storage import create_material

                    topics_csv = (handout_topic or "").strip() or None
                    user_id = st.session_state.get('user_id')
                    create_material(
                        filename=docx_title,
                        uploader_id=user_id,
                        topics=topics_csv,
                        path=str(save_path),
                        subject=handout_subject,
                        grade=handout_grade,
                    )
                    st.success(f"Раздаточный материал создан и сохранён: {docx_title}")
                    st.download_button("Скачать .docx", data=bytes_docx, file_name=docx_title, mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
                except Exception as e:
                    st.error(f"Ошибка при создании раздатки: {e}")

        if col2.button("Предзаполнить форму загрузки"):
            # заполним session_state аналогично админской форме
            st.session_state['upload_subject'] = handout_subject
            st.session_state['upload_grade'] = handout_grade
            st.session_state['upload_topic_prefill'] = handout_topic
            st.success("Форма загрузки предзаполнена. Перейдите в админ-панель для проверки (если есть доступ).")

    # ----- Вкладка: Викторина -----
    with tab_quiz:
        st.subheader("Создать шаблон викторины")
        quiz_title = st.text_input("Название викторины", value=st.session_state.get("gen_topic", ""))
        num_q = st.number_input("Число вопросов", min_value=1, max_value=50, value=5)
        if st.button("Скачать шаблон викторины (.json)"):
            quiz = {
                "title": quiz_title or "Викторина",
                "topic": st.session_state.get("gen_topic", ""),
                "questions": [{"question": "", "choices": [], "answer": None} for _ in range(int(num_q))]
            }
            data = json.dumps(quiz, ensure_ascii=False, indent=2).encode("utf-8")
            st.download_button("Скачать .json", data=data, file_name=f"{_slugify(quiz_title)}.json", mime="application/json")

    # Подсказка: быстрый поиск и просмотр материалов (как дополнительный блок)
    with st.expander("Поиск по материалам / AI-помощник"):
        query = st.text_input("Введите запрос для поиска по материалам и AI", key="search_query")
        if st.button("Поиск", key="search_btn"):
            if not query:
                st.warning("Введите запрос.")
            else:
                with st.spinner("🔍 Ищу..."):
                    results = []
                    if api_key:
                        try:
                            headers = {
                                "Authorization": f"Bearer {api_key}",
                                "Content-Type": "application/json",
                                "HTTP-Referer": "https://teacher-assistant.streamlit.app",
                                "X-Title": "Teacher Assistant Search"
                            }
                            data = {
                                "model": "deepseek/deepseek-chat",
                                "messages": [{"role": "user", "content": f"Помоги учителю найти: {query}"}],
                                "temperature": 0.5,
                                "max_tokens": 800,
                            }
                            resp = requests.post(DEEPSEEK_API_BASE, headers=headers, json=data, timeout=30)
                            resp.raise_for_status()
                            ai_response = resp.json()["choices"][0]["message"]["content"]
                            results.append({"title": f"AI: {query}", "snippet": ai_response, "type": "ai_response"})
                        except Exception:
                            pass

                    for p in materials_dir.glob("**/*"):
                        if query.lower() in p.name.lower():
                            results.append({"title": f"Файл: {p.name}", "snippet": str(p), "type": "local_file"})

                    if results:
                        for r in results:
                            with st.expander(r["title"]):
                                if r["type"] == "ai_response":
                                    st.markdown(r["snippet"])
                                else:
                                    st.write(r["snippet"])
                    else:
                        st.info("Ничего не найдено.")

elif app_mode == "Админ-панель":
    st.header("Админ-панель")
    if not is_admin():
        st.error("Доступ к админ-панели есть только у администратора.")
    else:
        st.subheader("Загрузка материалов")
        st.caption("Сначала выберите предмет и класс, затем загрузите файл КТП/материала.")
        upload_subject = st.selectbox("Предмет для загружаемых материалов", SUBJECTS, index=0, key="upload_subject")
        upload_grade = st.selectbox("Класс для загружаемых материалов (класс)", GRADES, index=3, key="upload_grade")
        uploaded_files = st.file_uploader(
            "Загрузите конспекты или раздаточные материалы",
            accept_multiple_files=True,
        )
        if uploaded_files:
            for f in uploaded_files:
                save_path = materials_dir / f.name
                with open(save_path, "wb") as out:
                    out.write(f.getbuffer())


                # Попытка извлечь темы из файла с помощью общего парсера
                suffix = save_path.suffix.lower()
                suggestions = []
                # Для PDF даём администратору возможность указать номер столбца
                if suffix == ".pdf":
                    col_key = f"{f.name}_pdf_col"
                    col = st.number_input("Номер колонки для извлечения тем (1-based)", min_value=1, max_value=10, value=2, key=col_key)
                    include_text_key = f"{f.name}_include_text"
                    include_text = st.checkbox("Включать извлечение из свободного текста (много шума)", value=False, key=include_text_key)
                    if st.button("Извлечь темы из PDF (по колонке)", key=f"extract_pdf_{f.name}"):
                        try:
                            suggestions = extract_topics_from_pdf_advanced(save_path, max_topics=500, column=col, include_text=include_text)
                            st.success(f"Найдено {len(suggestions)} темы(а) в PDF.")
                        except Exception as e:
                            st.error(f"Ошибка извлечения из PDF: {e}")
                # Если не PDF или не нажата кнопка — используем общий парсер
                if not suggestions:
                    suggestions = extract_topics(save_path, max_topics=50)

                # Извлекаем весь текст файла построчно для ручной правки
                full_lines = extract_full_text(save_path)

                st.write(f"Файл сохранён: {save_path}")
                st.caption("Отредактируйте строки и отметьте те, которые являются темами")

                # Список тем из существующих планов для выбора (выпадашки скрываем, если пусто)
                existing_plans = list_lesson_plans(limit=200)
                existing_topics = sorted({p.topic for p in existing_plans if p.topic})

                # Инициализация session_state для строк и чекбоксов
                for i, line in enumerate(full_lines):
                    key_text = f"{f.name}_text_{i}"
                    key_pick = f"{f.name}_pick_{i}"
                    if key_text not in st.session_state:
                        st.session_state[key_text] = line
                    # помечаем как предложенную тему, если строка похожа на suggestion
                    initial_pick = any(s.strip().lower() in line.strip().lower() for s in suggestions)
                    if key_pick not in st.session_state:
                        st.session_state[key_pick] = initial_pick

                # Инициализация session_state для тем, извлечённых из PDF (если есть)
                if suggestions:
                    st.session_state.setdefault(f"{f.name}_pdf_count", len(suggestions))
                    for i, t in enumerate(suggestions):
                        key_text = f"{f.name}_pdf_text_{i}"
                        key_pick = f"{f.name}_pdf_pick_{i}"
                        if key_text not in st.session_state:
                            st.session_state[key_text] = t
                        if key_pick not in st.session_state:
                            st.session_state[key_pick] = True

                with st.expander("Просмотр и разметка строк (нажмите, чтобы открыть)"):
                    for i, line in enumerate(full_lines):
                        key_text = f"{f.name}_text_{i}"
                        key_pick = f"{f.name}_pick_{i}"
                        col1, col2 = st.columns([0.08, 0.92])
                        with col1:
                            st.checkbox("", value=st.session_state.get(key_pick, False), key=key_pick)
                        with col2:
                            st.text_input(f"Строка {i+1}", key=key_text)

                # Отдельный блок для тем, извлечённых из PDF (если есть)
                if suggestions:
                    with st.expander("Темы, извлечённые из файла (проверить/править)"):
                        for i in range(st.session_state.get(f"{f.name}_pdf_count", 0)):
                            key_text = f"{f.name}_pdf_text_{i}"
                            key_pick = f"{f.name}_pdf_pick_{i}"
                            col1, col2 = st.columns([0.08, 0.92])
                            with col1:
                                st.checkbox("", value=st.session_state.get(key_pick, False), key=key_pick)
                            with col2:
                                st.text_input(f"Тема (из PDF) {i+1}", key=key_text)

                # Дополнительные возможности: добавить пустую строку как тему
                if st.button(f"Добавить пустую строку для {f.name}"):
                    idx = len(full_lines)
                    key_text = f"{f.name}_text_{idx}"
                    key_pick = f"{f.name}_pick_{idx}"
                    st.session_state[key_text] = ""
                    st.session_state[key_pick] = True
                    safe_rerun()

                if st.button(f"Сохранить метаданные для {f.name}"):
                    from storage import create_material

                    picks = []
                    for i in range(len(full_lines)):
                        key_text = f"{f.name}_text_{i}"
                        key_pick = f"{f.name}_pick_{i}"
                        if st.session_state.get(key_pick):
                            txt = st.session_state.get(key_text, "").strip()
                            if txt:
                                picks.append(txt)

                    topics_csv = ','.join(dict.fromkeys(picks)) if picks else None
                    user_id = st.session_state.get('user_id')
                    create_material(
                        filename=f.name,
                        uploader_id=user_id,
                        topics=topics_csv,
                        path=str(save_path),
                        subject=upload_subject,
                        grade=upload_grade,
                    )
                    st.success("Метаданные материала сохранены.")

            st.success(f"Сохранено {len(uploaded_files)} файл(ов) в папку {materials_dir}/")

        st.subheader("Материалы (обзор и управление)")
        topic_filter = st.text_input("Фильтр по темам материалов (подстрока)")
        materials = list_materials(limit=200)
        if not materials:
            st.info("Пока нет сохранённых метаданных материалов. Загрузите файлы выше или используйте bulk_upload.")
        else:
            for m in materials:
                if topic_filter and (not m.topics or topic_filter.lower() not in m.topics.lower()):
                    continue
                st.markdown(f"**{m.filename}**")
                st.caption(f"Темы: {m.topics or '—'}")
                if m.path and Path(m.path).exists():
                    with open(m.path, "rb") as fh:
                        st.download_button(
                            label="Скачать файл",
                            data=fh.read(),
                            file_name=Path(m.path).name,
                            key=f"material_download_{m.id}",
                        )

                if st.button("Удалить материал", key=f"delete_material_{m.id}"):
                    if m.path and Path(m.path).exists():
                        try:
                            os.remove(m.path)
                        except Exception:
                            pass

                    delete_material(m.id)
                    st.success("Материал удалён.")
                    safe_rerun()

                st.markdown("---")

st.caption(
    "Версия с генерацией планов уроков, базовой аутентификацией и загрузкой материалов. "
    "Далее можно добавить модерацию, публичный каталог и интеграцию с Deepseek/GPT API.",
)
