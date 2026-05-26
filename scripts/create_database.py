import os
from urllib.parse import urlparse

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv(".env")
load_dotenv("config/.env")


def _database_name(database_url: str) -> str:
    path = urlparse(database_url).path.lstrip("/")
    if not path:
        raise RuntimeError("DATABASE_URL must include a database name.")
    return path


def main() -> None:
    database_url = os.getenv("DATABASE_URL")
    admin_url = os.getenv("POSTGRES_ADMIN_URL")

    if not database_url or not admin_url:
        raise RuntimeError("DATABASE_URL and POSTGRES_ADMIN_URL must be set.")

    database_name = _database_name(database_url)
    engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")

    with engine.connect() as connection:
        exists = connection.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :database_name"),
            {"database_name": database_name},
        ).scalar()
        if not exists:
            connection.execute(text(f'CREATE DATABASE "{database_name}"'))
            print(f"Created database {database_name}")
        else:
            print(f"Database {database_name} already exists")


if __name__ == "__main__":
    main()
