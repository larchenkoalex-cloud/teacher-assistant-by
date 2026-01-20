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
)
from passlib.hash import bcrypt


st.set_page_config(page_title="Teacher Assistant", layout="wide")

# Инициализация БД (SQLite по умолчанию, можно заменить на Postgres через DATABASE_URL)
init_db()

st.title("Teacher Assistant — помощник для учителя")

st.sidebar.header("Настройки")
api_key = st.sidebar.text_input("Deepseek API key (опционально)", type="password")

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

materials_dir = Path(os.getenv("MATERIALS_DIR", "materials"))
materials_dir.mkdir(exist_ok=True)


def _slugify(value: str) -> str:
    """Простая функция для генерации безопасного имени файла."""

    value = value.strip().lower().replace(" ", "_")
    allowed = "abcdefghijklmnopqrstuvwxyz0123456789_-"
    return "".join(ch for ch in value if ch in allowed)[:60] or "lesson_plan"


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
    subject = st.text_input("Предмет", placeholder="Математика, История, Русский язык и т.д.")
    grade = st.text_input("Класс / курс", placeholder="5 класс, 10 класс, колледж...")
    topic = st.text_input("Тема урока", placeholder="Десятичные дроби", help="Ключевая тема занятия")
    notes = st.text_area("Особенности класса / пожелания", placeholder="Уровень класса, акценты, что важно подчеркнуть...")
    model_choice = st.selectbox(
        "Источник генерации",
        [
            "Локальный шаблон (без API)",
            "Deepseek API (через ключ)",
        ],
    )
    visibility = st.selectbox("Видимость плана", ["public", "private", "pending"], index=0)
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
        st.experimental_rerun()

st.header("Загрузка материалов")
uploaded_files = st.file_uploader(
    "Загрузите конспекты или раздаточные материалы",
    accept_multiple_files=True,
)
if uploaded_files:
    for f in uploaded_files:
        save_path = materials_dir / f.name
        with open(save_path, "wb") as out:
            out.write(f.getbuffer())
    st.success(f"Сохранено {len(uploaded_files)} файл(ов) в папку {materials_dir}/")

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

st.markdown("---")
st.caption(
    "Минимальная версия с генерацией планов уроков. Далее можно добавить аутентификацию, "
    "управление правами доступа и интеграцию с реальным Deepseek/GPT API.",
)
