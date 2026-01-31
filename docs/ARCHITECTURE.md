# Архитектура Teacher Assistant

Цель: сделать кодовую базу расширяемой и готовой к росту пользователей.

## Принципы

- `streamlit_app.py` — только UI и склейка. Бизнес‑логика уезжает в пакет `teacher_assistant/`.
- Слои зависимостей:
  - UI (`teacher_assistant/app`) → Services (`teacher_assistant/services`) → DB (`teacher_assistant/db`)
  - UI/Services могут использовать Utils (`teacher_assistant/utils`) и AI (`teacher_assistant/ai`).
- Избегаем «монолита»: переносим код постепенно, не ломая текущий запуск.

## Пакеты

- `teacher_assistant/ai` — клиенты LLM (OpenRouter и др.), стриминг, ретраи.
- `teacher_assistant/db` — модели/миграции/репозитории.
- `teacher_assistant/services` — бизнес‑операции (материалы, планы, викторины, поиск).
- `teacher_assistant/utils` — чистые утилиты (HTML/Markdown нормализация и т.п.).
- `teacher_assistant/app` — Streamlit‑хелперы, будущие страницы/роутинг.

## Документация по предметам

В `docs/subjects/` лежат подпапки по предметам. Там удобно хранить:
- требования/шаблоны промптов под предмет,
- методические заметки,
- примеры планов и критерии качества.
