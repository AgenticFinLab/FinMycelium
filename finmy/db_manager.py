"""
Implementation of using pandas to manage the database.
"""

from typing import Optional, Any, Dict

import pandas as pd
from sqlalchemy import create_engine


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
        engine: Optional[Any] = None,
        engine_config: Optional[Dict[str, Any]] = None,
    ):
        # Store the SQLAlchemy engine reference; may be set later via `set_engine`
        self.engine = engine if engine is not None else create_engine(**engine_config)

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
