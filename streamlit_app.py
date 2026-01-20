import os
from pathlib import Path

import streamlit as st
import requests


st.set_page_config(page_title="Teacher Assistant", layout="wide")

st.title("Teacher Assistant — помощник для учителя")

st.sidebar.header("Настройки")
api_key = st.sidebar.text_input("Deepseek API key (опционально)", type="password")

upload_dir = Path("materials")
upload_dir.mkdir(exist_ok=True)

st.header("Загрузка материалов")
uploaded_files = st.file_uploader("Загрузите конспекты или раздаточные материалы", accept_multiple_files=True)
if uploaded_files:
    for f in uploaded_files:
        save_path = upload_dir / f.name
        with open(save_path, "wb") as out:
            out.write(f.getbuffer())
    st.success(f"Сохранено {len(uploaded_files)} файл(ов) в папку materials/")

st.header("Разделы")
cols = st.columns(3)
with cols[0]:
    st.subheader("Конспекты")
    for p in sorted(upload_dir.glob("*.docx"))[:10]:
        st.write(p.name)
with cols[1]:
    st.subheader("Раздаточный материал")
    for p in sorted(upload_dir.glob("*.pdf"))[:10]:
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
                for p in upload_dir.glob("**/*"):
                    if query.lower() in p.name.lower():
                        results.append({"title": p.name, "snippet": f"Файл: {p}"})

            if results:
                for r in results:
                    st.markdown(f"**{r.get('title')}**")
                    st.write(r.get('snippet'))
            else:
                st.info("Ничего не найдено.")

st.markdown("---")
st.caption("Это минимальная версия. Далее можно добавить аутентификацию, управление правами доступа и интеграцию с реальным Deepseek API.")
