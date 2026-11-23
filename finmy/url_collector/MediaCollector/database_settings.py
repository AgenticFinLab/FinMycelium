"""Read connection settings when a collector starts, without changing the parent environment."""
import os
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy.engine import URL


def database_url():
    settings = {**dotenv_values(Path.cwd() / ".env"), **os.environ}
    dialect = (settings.get("DB_DIALECT") or "mysql").lower()
    if dialect not in {"mysql", "postgres", "postgresql"}:
        raise ValueError("Unsupported media database dialect")
    postgres = dialect != "mysql"
    return URL.create(
        "postgresql+psycopg" if postgres else "mysql+pymysql",
        username=settings.get("DB_USER"), password=settings.get("DB_PASSWORD"),
        host=settings.get("DB_HOST") or "127.0.0.1",
        port=int(settings.get("DB_PORT") or (5432 if postgres else 3306)),
        database=settings.get("DB_NAME") or "media_crawler",
        query={} if postgres else {"charset": settings.get("DB_CHARSET") or "utf8mb4"},
    )
