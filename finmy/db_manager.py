"""
Database layer helpers.

This module provides:

- `PDDataBaseManager`: a thin wrapper around pandas / SQLAlchemy
  for generic CSV / SQL IO.
- `DataManager`: a higher‑level helper tailored to FinMycelium's
  data model (`RawData`, `MetaSample`, `UserQueryInput`), roughly
  following the ER diagram in `docs/files/database-er.drawio`.

The goal is to keep all DB‑specific glue code in one place while
keeping the rest of the codebase focused on domain logic.
"""

import uuid
from typing import Optional, Any, Dict, List

import pandas as pd
from sqlalchemy import create_engine, text

from finmy.generic import RawData, MetaSample, UserQueryInput


class PDDataBaseManager:
    """Pandas-based manager for common data IO and simple SQL operations.

    Responsibilities:
    - Manage a shared SQLAlchemy engine for database read/write
    - Provide convenience wrappers around pandas IO (CSV/SQL)
    - Avoid altering business logic; this class focuses on IO plumbing

    Security:
    - Prefer parameterized queries via `read_sql_query` over raw `where` fragments
    - Do not pass untrusted user input directly into SQL strings
    """

    def __init__(
        self,
        engine_config: Dict[str, Any],
    ):
        """
        Initialize PDDataBaseManager.

        Args:
            engine_config: Configuration for creating new engine (optional)
        """

        self.engine = create_engine(**engine_config)

    def test_connection(self) -> bool:
        """
        Test database connection.

        Returns:
            True if connection successful, False otherwise
        """
        if self.engine is None:
            return False

        try:
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except Exception:
            return False

    def get_database_info(self) -> Dict[str, Optional[str]]:
        """
        Get database connection information (without password).

        Returns:
            Dictionary with database connection details
        """
        if self.engine is None:
            return {}

        # Extract information from engine URL
        url = str(self.engine.url)
        # Mask password for security
        if "@" in url:
            parts = url.split("@")
            user_part = parts[0]
            if ":" in user_part:
                user = user_part.split(":")[0].replace("mysql+pymysql://", "")
                url = url.replace(user_part, f"{user}:*****")

        return {
            "url": url,
            "dialect": self.engine.dialect.name,
            "driver": self.engine.dialect.driver,
            "database": self.engine.url.database,
            "host": self.engine.url.host,
            "port": str(self.engine.url.port),
            "username": self.engine.url.username,
        }

    def read_csv(self, path: str, **kwargs) -> pd.DataFrame:
        """Read a CSV file into a DataFrame using pandas.

        Supports standard pandas keyword arguments, e.g., `dtype`, `parse_dates`, `encoding`.
        """
        return pd.read_csv(path, **kwargs)

    def write_csv(
        self, df: pd.DataFrame, path: str, index: bool = False, **kwargs
    ) -> None:
        """Write a DataFrame to CSV.

        Set `index=True` to include DataFrame index in the output file.
        """
        df.to_csv(path, index=index, **kwargs)

    def read_sql_table(
        self,
        table_name: str,
        schema: Optional[str] = None,
        where: Optional[str] = None,
        **kwargs,
    ) -> pd.DataFrame:
        """Read a SQL table via pandas with optional simple filtering.

        Note:
        - The `where` argument is a raw SQL fragment; avoid passing untrusted input.
        - For complex or parameterized queries, prefer `read_sql_query`.
        """
        if self.engine is None:
            # Defensive: ensure engine is configured before DB access
            raise ValueError("Database engine is not set")
        if where:
            # Simple filter using a raw WHERE fragment
            sql = f"SELECT * FROM {table_name} WHERE {where}"
            return pd.read_sql_query(sql, self.engine, **kwargs)
        # Default: let pandas read the whole table, optionally within a schema
        return pd.read_sql_table(table_name, self.engine, schema=schema, **kwargs)

    def read_sql_query(
        self,
        sql: str,
        params: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> pd.DataFrame:
        """Execute an arbitrary SQL query; prefer using parameters when possible.

        Examples:
            read_sql_query("SELECT * FROM records WHERE company=%(name)s", params={"name": "ACME"})
        """
        if self.engine is None:
            raise ValueError("Database engine is not set")
        # Delegate to pandas; supports driver-appropriate parameter binding
        return pd.read_sql_query(sql, self.engine, params=params, **kwargs)

    def write_sql(
        self,
        df: pd.DataFrame,
        table_name: str,
        schema: Optional[str] = None,
        if_exists: str = "append",
        index: bool = False,
        **kwargs,
    ) -> None:
        """Write a DataFrame to a SQL table using pandas `to_sql`.

        Args:
            if_exists: One of 'fail' | 'replace' | 'append'
            index: Whether to write the DataFrame index as a column

        Tip:
            For very large DataFrames, consider `method='multi'` and `chunksize` in `**kwargs`.
        """
        if self.engine is None:
            raise ValueError("Database engine is not set")
        # Use the configured engine to persist the DataFrame
        df.to_sql(
            name=table_name,
            con=self.engine,
            schema=schema,
            if_exists=if_exists,
            index=index,
            **kwargs,
        )


class DataManager(PDDataBaseManager):
    """High-level manager for RAW_DATA / MEAT_SAMPLE / USER_QUERY tables.

    This class is a thin domain layer on top of `PDDataBaseManager`
    and assumes a relational schema compatible with the ER diagram
    in `docs/files/database-er.drawio`.

    Table conventions (can be adjusted later if needed):
    - RAW_DATA:
        raw_data_id (PK, str)
        source_file_path (str, optional)
        source_url (str, optional)
        location (str)
        time (str)
        copyright (str)
        method (str)
        tag (str)
    - MEAT_SAMPLE:
        sample_id (PK, str)
        raw_data_id (FK -> RAW_DATA.raw_data_id)
        location (str)
        time (str)
        category (str, nullable)
        knowledge_field (str, nullable)
        tag (str, nullable)
        method (str, nullable)
        reviews (JSON/text, nullable)
    - USER_QUERY:
        id (PK, str)
        query_text (text)
        key_words (JSON/text)
        time_range (JSON/text, nullable)
        extras (JSON/text, nullable)

    Notes:
    - We intentionally avoid hard SQLAlchemy models here and rely on
      simple pandas <-> table mappings to stay close to the existing
      `PDDataBaseManager` design.
    - JSON-like fields are stored as text using `repr()` by default;
      you can switch to a proper JSON column later if desired.
    """

    TABLE_RAW_DATA = "RAW_DATA"
    TABLE_MEAT_SAMPLE = "MEAT_SAMPLE"
    TABLE_USER_QUERY = "USER_QUERY"

    # ---------- RAW_DATA ----------

    def insert_raw_data(self, raw: RawData) -> dict:
        """Insert a single `RawData` record into `RAW_DATA`.

        For now we map:
        - `raw.source` -> both `source_file_path` and `source_url`
          (the caller can later refine the schema if needed).
        """
        record = {
            "raw_data_id": raw.raw_data_id if raw.raw_data_id else str(uuid.uuid4()),
            "source_file_path": raw.source,
            "source_url": raw.source,
            "location": raw.location,
            "time": raw.time,
            "copyright": raw.data_copyright,
            "method": raw.method,
            "tag": raw.tag,
        }
        df = pd.DataFrame([record])
        self.write_sql(
            df, table_name=self.TABLE_RAW_DATA, if_exists="append", index=False
        )
        return record

    def insert_raw_data_batch(self, raws: List[RawData]) -> dict:
        """Batch insert multiple `RawData` records."""
        if not raws:
            return
        records = []
        for raw in raws:
            records.append(
                {
                    "raw_data_id": (
                        raw.raw_data_id if raw.raw_data_id else str(uuid.uuid4())
                    ),
                    "source_file_path": raw.source,
                    "source_url": raw.source,
                    "location": raw.location,
                    "time": raw.time,
                    "copyright": raw.data_copyright,
                    "method": raw.method,
                    "tag": raw.tag,
                }
            )
        df = pd.DataFrame(records)
        self.write_sql(
            df, table_name=self.TABLE_RAW_DATA, if_exists="append", index=False
        )
        return records

    # ---------- MEAT_SAMPLE ----------

    def insert_meta_samples(self, samples: List[MetaSample]) -> list:
        """Batch insert `MetaSample` records into `MEAT_SAMPLE`."""
        if not samples:
            return

        records = []
        for s in samples:
            records.append(
                {
                    "sample_id": s.sample_id if s.sample_id else str(uuid.uuid4()),
                    "raw_data_id": s.raw_data_id,
                    "location": s.location,
                    "time": s.time,
                    "category": s.category,
                    "knowledge_field": s.knowledge_field,
                    "tag": s.tag,
                    "method": s.method,
                    # store reviews as a simple text representation
                    "reviews": repr(s.reviews) if s.reviews is not None else None,
                }
            )

        df = pd.DataFrame(records)
        self.write_sql(
            df, table_name=self.TABLE_MEAT_SAMPLE, if_exists="append", index=False
        )

        return records

    # ---------- USER_QUERY ----------

    def insert_user_query(self, uq: UserQueryInput) -> dict:
        """Insert a `UserQueryInput` into `USER_QUERY`.

        Args:
            uq: `UserQueryInput` dataclass instance.
            query_id: unique identifier for this query (typically a UUID).
        """
        record = {
            "user_query_id": (
                uq.user_query_id if uq.user_query_id else str(uuid.uuid4())
            ),
            "query_text": uq.query_text,
            "key_words": repr(uq.key_words),
            "time_range": repr(uq.time_range),
            "extras": repr(uq.extras),
        }
        df = pd.DataFrame([record])
        self.write_sql(
            df, table_name=self.TABLE_USER_QUERY, if_exists="append", index=False
        )
        return record

    # Simple query helpers -------------------------------------------------

    def fetch_raw_data_by_id(self, raw_data_id: str) -> pd.DataFrame:
        """Fetch `RAW_DATA` rows by `raw_data_id`."""
        where = f"raw_data_id = '{raw_data_id}'"
        return self.read_sql_table(self.TABLE_RAW_DATA, where=where)

    def fetch_samples_by_raw_id(self, raw_data_id: str) -> pd.DataFrame:
        """Fetch `MEAT_SAMPLE` rows linked to a given `raw_data_id`."""
        where = f"raw_data_id = '{raw_data_id}'"
        return self.read_sql_table(self.TABLE_MEAT_SAMPLE, where=where)

    def fetch_user_query_by_id(self, user_query_id: str) -> pd.DataFrame:
        """Fetch `USER_QUERY` rows by `user_query_id`."""
        where = f"user_query_id = '{user_query_id}'"
        return self.read_sql_table(self.TABLE_USER_QUERY, where=where)
