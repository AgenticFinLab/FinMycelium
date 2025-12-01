"""
Implementation of using pandas to manage the database.
"""

import os
from typing import Optional, Any, Dict
from pathlib import Path
from dotenv import load_dotenv

import pandas as pd
from sqlalchemy import create_engine, text


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
        env_path: Optional[str] = None,
    ):
        """
        Initialize PDDataBaseManager.

        Args:
            engine: Existing SQLAlchemy engine (optional)
            engine_config: Configuration for creating new engine (optional)
            env_path: Path to .env file (defaults to root directory)
        """
        if engine is not None:
            # Use provided engine if available
            self.engine = engine
        elif engine_config is not None:
            # Use provided configuration
            self.engine = create_engine(**engine_config)
        else:
            # Load database configuration from .env file
            self.engine = self._create_engine_from_env(env_path)

    def _create_engine_from_env(self, env_path: Optional[str] = None) -> Any:
        """
        Create SQLAlchemy engine from .env file configuration.

        Args:
            env_path: Path to .env file (defaults to root directory)

        Returns:
            SQLAlchemy engine instance

        Raises:
            FileNotFoundError: If .env file is not found
            ValueError: If required environment variables are missing
        """
        # Determine .env file path
        if env_path is None:
            # Try root directory by default
            env_path = Path.cwd() / ".env"
        else:
            env_path = Path(env_path)

        # Load environment variables
        if not env_path.exists():
            raise FileNotFoundError(f".env file not found at: {env_path}")

        load_dotenv(dotenv_path=env_path)

        # Get database configuration
        db_host = os.getenv("DB_HOST")
        db_port = os.getenv("DB_PORT")
        db_name = os.getenv("DB_NAME")
        db_user = os.getenv("DB_USER")
        db_password = os.getenv("DB_PASSWORD")
        db_charset = os.getenv("DB_CHARSET", "utf8")

        # Validate required variables
        required_vars = {
            "DB_HOST": db_host,
            "DB_PORT": db_port,
            "DB_NAME": db_name,
            "DB_USER": db_user,
            "DB_PASSWORD": db_password,
        }

        missing_vars = [var for var, value in required_vars.items() if not value]
        if missing_vars:
            raise ValueError(
                f"Missing required environment variables: {', '.join(missing_vars)}"
            )

        # Construct database URL
        # Format: dialect+driver://username:password@host:port/database?charset=charset
        db_url = f"mysql+pymysql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}?charset={db_charset}"

        # Create and return engine
        return create_engine(db_url, echo=False)  # Set echo=True for debug logging

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
