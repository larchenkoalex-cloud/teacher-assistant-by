# Teacher Assistant — бесплатный помощник для учителей

Проект: централизованный ресурс для учителей Беларуси — конспекты уроков, раздаточные материалы и викторины.

Коротко:
- Минимальная версия — Streamlit-приложение (`streamlit_app.py`).
- Для деплоя на share.streamlit.io нужен публичный репозиторий и `requirements.txt`.

## Структура проекта (для масштабирования)

- `teacher_assistant/` — основной пакет (сюда постепенно переносим логику из `streamlit_app.py`):
	- `teacher_assistant/ai/` — клиенты LLM (OpenRouter), стриминг
	- `teacher_assistant/utils/` — утилиты (например подготовка HTML для Quill)
	- `teacher_assistant/app/` — Streamlit-хелперы и будущие страницы
- `docs/` — документация
	- `docs/subjects/` — подпапки по предметам (промпты/критерии/примеры)

Как запустить локально:

1. Создать виртуальное окружение и установить зависимости:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run streamlit_app.py
```

Deepseek API:
- В приложении предусмотрена заглушка для поиска; после получения доступа к API замените реализацию в `streamlit_app.py`.

Лицензия: MIT (подробности в `LICENSE`).

Контакты: владелец репозитория — larchenkoalex-cloud.
