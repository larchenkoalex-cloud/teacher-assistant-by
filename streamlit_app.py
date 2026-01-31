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

from storage import (
    LessonPlan,
    create_lesson_plan,
    init_db,
    list_lesson_plans,
    create_user,
    get_user_by_username,
    list_materials,
    delete_material,
)
from passlib.hash import bcrypt

from parsers import extract_topics, extract_full_text
import json


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


def safe_rerun() -> None:
    """Безопасно перезапускает скрипт Streamlit с несколькими fallback-опциями.

    В некоторых версиях Streamlit `st.experimental_rerun` может быть недоступен.
    Пытаемся вызвать его, затем пытаемся поднять внутреннее `RerunException`,
    а если и это не работает — помечаем `st.session_state` и вызываем `st.stop()`.
    """
    try:
        st.experimental_rerun()
    except Exception:
        try:
            from streamlit.runtime.scriptrunner.script_runner import RerunException

            raise RerunException()
        except Exception:
            st.session_state["_rerun_indicator"] = st.session_state.get("_rerun_indicator", 0) + 1
            st.stop()


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
    buffer = ""
    data = {
        "model": model,
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 2000,
        "stream": True,
    }

    try:
        resp = requests.post(DEEPSEEK_API_BASE, headers=headers, json=data, timeout=60, stream=True)
        resp.raise_for_status()

        # Принудительно декодируем как UTF-8 — это предотвращает «mojibake»
        # когда сервер/прокси отдает байты UTF-8, а requests пытается декодировать в latin-1.
        resp.encoding = "utf-8"

        content_type = (resp.headers.get("content-type") or "").lower()
        if "text/event-stream" not in content_type:
            # Не SSE — обычный JSON
            result = resp.json()
            return result["choices"][0]["message"]["content"]

        for chunk in resp.iter_lines(decode_unicode=True):
            if not chunk:
                continue
            line = chunk.strip()
            if line.startswith("data:"):
                line = line[len("data:"):].strip()
            if not line or line == "[DONE]":
                continue

            try:
                payload = json.loads(line)
            except Exception:
                continue

            for choice in payload.get("choices", []):
                delta = choice.get("delta") or {}
                piece = delta.get("content")
                if piece:
                    buffer += piece

            # Обновляем превью по мере поступления (рендерим Markdown, а не сырой текст)
            placeholder.markdown(_postprocess_plan_text(buffer))

        return buffer
    except Exception:
        return buffer


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
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://teacher-assistant.streamlit.app",
        "X-Title": "Teacher Assistant",
    }


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


def _build_lesson_plan_messages(*, subject: str, grade: str, topic: str, lesson_type: str, class_level: str, notes: str) -> list:
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

    typed = st.session_state.get("gen_topic", "") or ""
    if typed:
        matches = [t for t in topic_candidates if typed.lower() in t.lower()]
        matches = sorted(matches)[:10]
        if matches:
            st.caption("Возможные темы из КТП и планов:")
            for i, t in enumerate(matches):
                if st.button(t, key=f"suggest_topic_{i}"):
                    st.session_state["gen_topic"] = t
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
            # Локальная генерация возвращает Markdown — конвертируем в HTML для визуального редактора.
            st.session_state["editor_html"] = _markdown_to_html(_postprocess_plan_text(plan_text))
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
            st.session_state["editor_html"] = _markdown_to_html(_postprocess_plan_text(full_text))
            st.session_state["editor_instance"] = st.session_state.get("editor_instance", 0) + 1
            st.session_state["is_generating"] = False

        stream_buffer = st.session_state.get("stream_buffer", "")
        if stream_buffer:
            stream_placeholder.markdown(_postprocess_plan_text(stream_buffer))

    if not st.session_state.get("is_generating"):
        # Если есть сгенерированный план (из предыдущего запуска), переместим его в editor_* перед созданием виджетов
        if "generated_content" in st.session_state:
            raw = st.session_state.pop("generated_content")
            # В генерации приходит Markdown — конвертируем в HTML для визуального редактора.
            st.session_state["editor_html"] = _markdown_to_html(_postprocess_plan_text(raw))
            st.session_state["editor_instance"] = st.session_state.get("editor_instance", 0) + 1
        if "generated_title" in st.session_state:
            st.session_state["editor_title"] = st.session_state.pop("generated_title")

        # Инициализация содержимого редактора в session_state по умолчанию
        if "editor_title" not in st.session_state:
            st.session_state["editor_title"] = ""

        if "editor_instance" not in st.session_state:
            st.session_state["editor_instance"] = 0

        # Поле заголовка и сам редактор (WYSIWYG)
        st.text_input("Заголовок плана", key="editor_title")

        if st_quill is None:
            st.error("Визуальный редактор недоступен: пакет streamlit-quill не установлен.")
            st.stop()

        if "editor_html" not in st.session_state:
            st.session_state["editor_html"] = ""

        html_value = st_quill(
            value=st.session_state.get("editor_html", ""),
            html=True,
            key=f"editor_quill_{st.session_state.get('editor_instance', 0)}",
        )
        if html_value is not None:
            # Сохраняем сырой HTML, без дополнительной серверной очистки или перерисовки редактора.
            st.session_state["editor_html"] = html_value

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
    st.header("Разделы")
    cols = st.columns(3)
    with cols[0]:
        st.subheader("Конспекты")
        for p in sorted(materials_dir.glob("*.docx"))[:10]:
            st.write(p.name)
    with cols[1]:
        st.subheader("Раздаточный материал")
        for p in sorted(materials_dir.glob("*.pdf"))[:10]:
            st.write(p.name)
    with cols[2]:
        st.subheader("Викторины")
        st.write("Добавьте викторины в формате .json или .csv")

    st.header("Поиск по материалам / Deepseek")
    query = st.text_input("Введите запрос")
    if st.button("Поиск"):
        if not query:
            st.warning("Введите запрос.")
        else:
            with st.spinner("🔍 Ищу информацию с помощью DeepSeek AI..."):
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
                            "messages": [{
                                "role": "user", 
                                "content": f"""Помоги учителю найти информацию по запросу: "{query}".
                                
                                Предоставь:
                                1. Краткий ответ на запрос
                                2. 3-5 ключевых идей/понятий
                                3. Практические рекомендации для урока
                                4. Источники для дополнительного изучения
                                
                                Будь конкретен и полезен для педагога."""
                            }],
                            "temperature": 0.5,
                            "max_tokens": 1000
                        }
                        
                        resp = requests.post(
                            DEEPSEEK_API_BASE,
                            headers=headers,
                            json=data,
                            timeout=30
                        )
                        
                        if show_deepseek_debug:
                            st.markdown(f"**Search API — HTTP:** {resp.status_code}")
                        
                        resp.raise_for_status()
                        ai_response = resp.json()["choices"][0]["message"]["content"]
                        
                        results.append({
                            "title": f"🤖 AI ответ на запрос: '{query}'",
                            "snippet": ai_response,
                            "type": "ai_response"
                        })
                        
                    except Exception as e:
                        if show_deepseek_debug:
                            st.error(f"Ошибка AI поиска: {e}")
                
                # Также ищем в локальных материалах
                for p in materials_dir.glob("**/*"):
                    if query.lower() in p.name.lower():
                        results.append({
                            "title": f"📄 {p.name}",
                            "snippet": f"Файл: {p}",
                            "type": "local_file"
                        })
                
                # Показываем результаты
                if results:
                    st.subheader(f"Найдено {len(results)} результат(ов)")
                    for r in results:
                        with st.expander(r["title"]):
                            if r.get("type") == "ai_response":
                                st.markdown(r["snippet"])
                            else:
                                st.write(r["snippet"])
                                file_path = r["snippet"].replace("Файл: ", "")
                                if Path(file_path).exists():
                                    with open(file_path, "rb") as f:
                                        st.download_button(
                                            "Скачать файл",
                                            f.read(),
                                            file_name=Path(file_path).name
                                        )
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

                with st.expander("Просмотр и разметка строк (нажмите, чтобы открыть)"):
                    for i, line in enumerate(full_lines):
                        key_text = f"{f.name}_text_{i}"
                        key_pick = f"{f.name}_pick_{i}"
                        col1, col2 = st.columns([0.08, 0.92])
                        with col1:
                            st.checkbox("", value=st.session_state.get(key_pick, False), key=key_pick)
                        with col2:
                            st.text_input(f"Строка {i+1}", key=key_text)

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
