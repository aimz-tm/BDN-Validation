import os
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv(".env")
load_dotenv("config/.env")


@lru_cache
def get_database_url() -> str:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError(
            "DATABASE_URL is not set. Copy .env.example to .env or config/.env and update the credentials."
        )
    return database_url
