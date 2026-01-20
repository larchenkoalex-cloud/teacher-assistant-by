from pathlib import Path

from parsers import extract_topics
from storage import create_material, get_user_by_username, init_db


def main() -> None:
    init_db()

    admin_username = "admin"  # TODO: заменить на реального администратора
    user = get_user_by_username(admin_username)
    if not user:
        raise SystemExit(f"User '{admin_username}' not found. Создайте пользователя и повторите.")

    uploader_id = user.id

    folder = Path("bulk_materials")
    if not folder.exists():
        raise SystemExit(f"Папка {folder} не найдена. Создайте её и положите файлы.")

    created = 0
    for path in folder.iterdir():
        if not path.is_file():
            continue
        topics = extract_topics(path, max_topics=20)
        topics_csv = ",".join(topics)
        create_material(
            filename=path.name,
            uploader_id=uploader_id,
            topics=topics_csv or None,
            path=str(path),
        )
        created += 1

    print(f"Создано {created} материалов из папки {folder}.")


if __name__ == "__main__":
    main()
