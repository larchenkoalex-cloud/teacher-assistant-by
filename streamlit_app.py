import os
from datetime import datetime
from pathlib import Path

import requests
import streamlit as st

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
from pathlib import Path

from parsers import extract_topics, extract_full_text


IS_DEV_ADMIN = True  # в режиме разработки считаем текущего пользователя администратором

SUBJECTS = [
    "Математика",
    "Русский язык",
    "Литература",
    "Белорусский язык",
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

st.sidebar.header("Настройки")
api_key = st.sidebar.text_input("Deepseek API key (опционально)", type="password")

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


def generate_lesson_plan_locally(subject: str, grade: str, topic: str, notes: str) -> str:
    """Локальная заготовка плана урока на случай отсутствия API."""

    header = f"План урока по предмету: {subject} (класс: {grade})\nТема: {topic}\n\n"
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


st.header("Генерация плана урока (ИИ)")
col_form, col_preview = st.columns(2)

with col_form:
    subject = st.selectbox("Предмет", SUBJECTS, index=0, key="gen_subject")
    grade = st.selectbox("Класс / курс", GRADES, index=3, key="gen_grade")
    topic = st.text_input("Тема урока", placeholder="Десятичные дроби", help="Ключевая тема занятия", key="gen_topic")
    notes = st.text_area("Особенности класса / пожелания", placeholder="Уровень класса, акценты, что важно подчеркнуть...")
    model_choice = st.selectbox(
        "Источник генерации",
        [
            "Локальный шаблон (без API)",
            "Deepseek API (через ключ)",
        ],
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

with col_preview:
    st.subheader("Последние сохранённые планы уроков")
    plans = list_lesson_plans(limit=10)
    if plans:
        for plan in plans:
            meta = f"{plan.subject or 'Без предмета'} — {plan.grade or 'Без класса'}"
            created = plan.created_at.strftime("%d.%m.%Y %H:%M") if plan.created_at else ""
            st.markdown(f"**{plan.title}**  ")
            st.caption(f"{meta} | создан: {created} | источник: {plan.model_name or 'не указан'}")
            with st.expander("Показать план"):
                st.markdown(plan.content)
                st.download_button(
                    label="Скачать как .md",
                    data=plan.content,
                    file_name=f"{_slugify(plan.title)}.md",
                    mime="text/markdown",
                    key=f"download_{plan.id}",
                )
    else:
        st.info("Пока нет сохранённых планов. Сгенерируйте первый план слева.")

if generate_clicked:
    if not subject or not topic:
        st.warning("Укажите хотя бы предмет и тему урока.")
    else:
        with st.spinner("Генерирую план урока..."):
            model_name = "local-template"
            model_version = None

            if model_choice == "Deepseek API (через ключ)" and api_key:
                try:
                    # Примерный вызов Deepseek API — нужно будет заменить на реальный endpoint
                    resp = requests.post(
                        "https://api.deepseek.example/lesson-plan",
                        headers={"Authorization": f"Bearer {api_key}"},
                        json={
                            "subject": subject,
                            "grade": grade,
                            "topic": topic,
                            "notes": notes,
                        },
                        timeout=30,
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    plan_text = data.get("plan") or generate_lesson_plan_locally(subject, grade, topic, notes)
                    model_name = data.get("model_name") or "deepseek"
                    model_version = data.get("model_version")
                except Exception:
                    st.warning("Не удалось получить ответ от Deepseek API. Использую локальный шаблон.")
                    plan_text = generate_lesson_plan_locally(subject, grade, topic, notes)
            else:
                plan_text = generate_lesson_plan_locally(subject, grade, topic, notes)

            title = f"{subject or 'Урок'} — {topic}"[:200]
            status = "published" if visibility == "public" else ("pending" if visibility == "pending" else "private")
            create_lesson_plan(
                title=title,
                subject=subject,
                grade=grade,
                topic=topic,
                tags=None,
                content=plan_text,
                model_name=model_name,
                model_version=model_version,
                author_id=st.session_state.get("user_id"),
                visibility=visibility,
                status=status,
            )

        st.success("План урока сохранён.")
        safe_rerun()

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
            with st.spinner("Выполняю поиск..."):
                results = []
                # Заглушка для Deepseek — замените на реальную реализацию
                if api_key:
                    try:
                        # Пример вызова — замените URL/параметры под реальный API
                        resp = requests.post(
                            "https://api.deepseek.example/search",
                            headers={"Authorization": f"Bearer {api_key}"},
                            json={"query": query},
                            timeout=10,
                        )
                        resp.raise_for_status()
                        results = resp.json().get("results", [])
                    except Exception:
                        results = [{"title": "(заглушка) Результат A", "snippet": "Проверьте конфигурацию Deepseek API."}]
                else:
                    # Локальная имитация поиска по названиям файлов
                    for p in materials_dir.glob("**/*"):
                        if query.lower() in p.name.lower():
                            results.append({"title": p.name, "snippet": f"Файл: {p}"})

                if results:
                    for r in results:
                        st.markdown(f"**{r.get('title')}**")
                        st.write(r.get('snippet'))
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
        upload_grade = st.selectbox("Класс для загружаемых материалов", GRADES, index=3, key="upload_grade")
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
