"""Миграция: добавляет колонки `subject` и `grade` в таблицу `materials` для SQLite.

Запуск:
    python scripts/migrate_add_material_columns.py

Если проект использует другую БД (Postgres и т.п.), выполните миграцию через Alembic или вручную.
"""
import os
import sqlite3
from urllib.parse import urlparse

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///teacher_assistant.db")


def is_sqlite(url: str) -> bool:
    return url.startswith("sqlite")


def sqlite_path_from_url(url: str) -> str:
    # url like sqlite:///relative/path.db or sqlite:////absolute/path.db
    if url.startswith("sqlite:///"):
        path = url[len("sqlite:///"):]
        return path
    if url.startswith("sqlite:////"):
        return "/" + url[len("sqlite:////"):]
    raise RuntimeError("Не удалось распознать путь SQLite в DATABASE_URL")


def table_has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    cur = conn.execute(f"PRAGMA table_info('{table}')")
    cols = [r[1] for r in cur.fetchall()]
    return column in cols


def migrate_sqlite(db_path: str) -> None:
    if not os.path.exists(db_path):
        print(f"БД не найдена по пути: {db_path}. Таблицы будут созданы при запуске приложения.")
        return

    conn = sqlite3.connect(db_path)
    try:
        changed = False
        if not table_has_column(conn, 'materials', 'subject'):
            conn.execute("ALTER TABLE materials ADD COLUMN subject TEXT")
            print("Добавлена колонка 'subject' в таблицу 'materials'.")
            changed = True
        else:
            print("Колонка 'subject' уже существует.")

        if not table_has_column(conn, 'materials', 'grade'):
            conn.execute("ALTER TABLE materials ADD COLUMN grade TEXT")
            print("Добавлена колонка 'grade' в таблицу 'materials'.")
            changed = True
        else:
            print("Колонка 'grade' уже существует.")

        if changed:
            conn.commit()
            print("Миграция завершена успешно.")
        else:
            print("Изменений не требуется.")
    finally:
        conn.close()


def main():
    print(f"DATABASE_URL={DATABASE_URL}")
    if not is_sqlite(DATABASE_URL):
        print("DATABASE_URL не указывает на SQLite. Для других СУБД выполните миграцию вручную или через Alembic.")
        return

    db_path = sqlite_path_from_url(DATABASE_URL)
    print(f"Использую SQLite файл: {db_path}")
    # Рекомендуемая дополнительная безопасность: создать резервную копию
    backup = db_path + ".backup"
    if os.path.exists(db_path) and not os.path.exists(backup):
        try:
            import shutil

            shutil.copy2(db_path, backup)
            print(f"Создана резервная копия БД: {backup}")
        except Exception as e:
            print(f"Не удалось создать бэкап: {e}")

    migrate_sqlite(db_path)


if __name__ == '__main__':
    main()
