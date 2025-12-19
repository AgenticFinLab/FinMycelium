"""
Data Manager.

This module provides a unified interface to access and manage various data tables
from the database, including table metadata and sample data retrieval.
"""

from typing import Dict, List, Any, Optional

import pandas as pd

from finmy.db_manager import PDDataBaseManager


class DataManager:
    """Manager for database table data integration and access.

    This class provides methods to:
    1. Discover and list all available tables in the database
    2. Retrieve table structure (columns and data types)
    3. Get sample data from tables
    4. Provide unified access to different data sources
    """

    def __init__(self, db_manager: PDDataBaseManager):
        """
        Initialize DataManager with a database manager instance.

        Args:
            db_manager: An instance of PDDataBaseManager for database operations
        """
        if not isinstance(db_manager, PDDataBaseManager):
            raise TypeError("db_manager must be an instance of PDDataBaseManager")

        self.db_manager = db_manager
        # Cache for table information to avoid repeated queries
        self._table_info_cache = {}

    def test_connection(self) -> bool:
        """
        Test the database connection.

        Returns:
            bool: True if connection is successful, False otherwise
        """
        return self.db_manager.test_connection()

    def get_database_info(self) -> Dict[str, str]:
        """
        Get database connection information.

        Returns:
            Dict containing database connection details
        """
        return self.db_manager.get_database_info()

    def list_all_tables(self, refresh: bool = False) -> List[str]:
        """
        Retrieve all table names from the database.

        Args:
            refresh: If True, force refresh the table list from database

        Returns:
            List of table names

        Raises:
            ConnectionError: If database connection fails
        """
        if not refresh and "tables" in self._table_info_cache:
            return list(self._table_info_cache.keys())

        # Test connection first
        if not self.test_connection():
            raise ConnectionError("Cannot connect to database")

        # Query to get all table names
        # Note: This assumes MySQL. For other databases, adjust the query accordingly.
        query = """
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = DATABASE()
        AND table_type = 'BASE TABLE'
        ORDER BY table_name
        """

        try:
            df_tables = self.db_manager.read_sql_query(query)
            tables = df_tables["table_name"].tolist()

            # Initialize cache for each table
            for table in tables:
                if table not in self._table_info_cache:
                    self._table_info_cache[table] = {}

            return tables

        except Exception as e:
            raise RuntimeError(f"Failed to retrieve table list: {str(e)}")

    def get_table_schema(self, table_name: str, refresh: bool = False) -> pd.DataFrame:
        """
        Get the schema (columns and data types) of a specific table.

        Args:
            table_name: Name of the table to inspect
            refresh: If True, force refresh schema from database

        Returns:
            DataFrame with columns: ['column_name', 'data_type', 'is_nullable', 'column_default']

        Raises:
            ValueError: If table does not exist
            ConnectionError: If database connection fails
        """
        if not self.test_connection():
            raise ConnectionError("Cannot connect to database")

        # Check if table exists
        all_tables = self.list_all_tables(refresh=refresh)
        if table_name not in all_tables:
            raise ValueError(
                f"Table '{table_name}' does not exist in the database. "
                f"Available tables: {', '.join(all_tables)}"
            )

        # Return cached schema if available and not refreshing
        if (
            not refresh
            and table_name in self._table_info_cache
            and "schema" in self._table_info_cache[table_name]
        ):
            return self._table_info_cache[table_name]["schema"].copy()

        # Query to get table schema
        query = """
        SELECT 
            column_name,
            data_type,
            is_nullable,
            column_default
        FROM information_schema.columns 
        WHERE table_schema = DATABASE()
        AND table_name = %(table_name)s
        ORDER BY ordinal_position
        """

        try:
            schema_df = self.db_manager.read_sql_query(
                query, params={"table_name": table_name}
            )

            # Cache the schema
            if table_name not in self._table_info_cache:
                self._table_info_cache[table_name] = {}
            self._table_info_cache[table_name]["schema"] = schema_df.copy()

            return schema_df

        except Exception as e:
            raise RuntimeError(
                f"Failed to retrieve schema for table '{table_name}': {str(e)}"
            )

    def get_table_sample(
        self, table_name: str, sample_size: int = 5, columns: Optional[List[str]] = None
    ) -> pd.DataFrame:
        """
        Get a sample of data from a specific table.

        Args:
            table_name: Name of the table to sample
            sample_size: Number of rows to retrieve (default: 5)
            columns: Specific columns to retrieve. If None, retrieves all columns.

        Returns:
            DataFrame containing sample data

        Raises:
            ValueError: If table does not exist or sample_size is invalid
            ConnectionError: If database connection fails
        """
        if sample_size <= 0:
            raise ValueError("sample_size must be greater than 0")

        if not self.test_connection():
            raise ConnectionError("Cannot connect to database")

        # Check if table exists
        all_tables = self.list_all_tables()
        if table_name not in all_tables:
            raise ValueError(
                f"Table '{table_name}' does not exist in the database. "
                f"Available tables: {', '.join(all_tables)}"
            )

        # Build SELECT clause
        if columns:
            # Validate that columns exist in the table
            schema = self.get_table_schema(table_name)
            table_columns = schema["column_name"].tolist()
            invalid_columns = [col for col in columns if col not in table_columns]

            if invalid_columns:
                raise ValueError(
                    f"Columns not found in table '{table_name}': {invalid_columns}"
                )

            columns_str = ", ".join([f"`{col}`" for col in columns])
            select_clause = f"SELECT {columns_str}"
        else:
            select_clause = "SELECT *"

        # Build query
        query = f"""
        {select_clause}
        FROM `{table_name}`
        LIMIT %(limit)s
        """

        try:
            sample_df = self.db_manager.read_sql_query(
                query, params={"limit": sample_size}
            )

            # Cache the sample
            if table_name not in self._table_info_cache:
                self._table_info_cache[table_name] = {}
            self._table_info_cache[table_name]["sample"] = sample_df.copy()

            return sample_df

        except Exception as e:
            raise RuntimeError(
                f"Failed to retrieve sample from table '{table_name}': {str(e)}"
            )

    def get_table_info(
        self, table_name: str, include_sample: bool = True, sample_size: int = 3
    ) -> Dict[str, Any]:
        """
        Get comprehensive information about a table.

        Args:
            table_name: Name of the table
            include_sample: Whether to include sample data
            sample_size: Number of sample rows to include (if include_sample is True)

        Returns:
            Dictionary containing table information:
            - 'name': Table name
            - 'exists': Whether table exists
            - 'row_count': Number of rows in table
            - 'schema': DataFrame with column information
            - 'sample': DataFrame with sample data (if include_sample is True)
            - 'columns': List of column names
        """
        if not self.test_connection():
            raise ConnectionError("Cannot connect to database")

        all_tables = self.list_all_tables()

        info = {"name": table_name, "exists": table_name in all_tables}

        if info["exists"]:
            # Get schema
            info["schema"] = self.get_table_schema(table_name)
            info["columns"] = info["schema"]["column_name"].tolist()

            # Get row count
            count_query = f"SELECT COUNT(*) as row_count FROM `{table_name}`"
            count_df = self.db_manager.read_sql_query(count_query)
            info["row_count"] = count_df["row_count"].iloc[0]

            # Get sample data if requested
            if include_sample:
                info["sample"] = self.get_table_sample(
                    table_name, sample_size=sample_size
                )

        return info

    def get_all_tables_info(
        self, include_samples: bool = False, sample_size: int = 2
    ) -> Dict[str, Dict[str, Any]]:
        """
        Get information for all tables in the database.

        Args:
            include_samples: Whether to include sample data for each table
            sample_size: Number of sample rows for each table (if include_samples is True)

        Returns:
            Dictionary where keys are table names and values are table info dictionaries

        Raises:
            ConnectionError: If database connection fails
        """
        if not self.test_connection():
            raise ConnectionError("Cannot connect to database")

        all_tables = self.list_all_tables()
        tables_info = {}

        for table_name in all_tables:
            try:
                tables_info[table_name] = self.get_table_info(
                    table_name, include_sample=include_samples, sample_size=sample_size
                )
            except Exception as e:
                # Log error but continue with other tables
                tables_info[table_name] = {
                    "name": table_name,
                    "exists": True,
                    "error": str(e),
                }

        return tables_info

    def summarize_database(self) -> Dict[str, Any]:
        """
        Create a summary of the entire database.

        Returns:
            Dictionary containing database summary:
            - 'database_info': Database connection information
            - 'table_count': Number of tables
            - 'tables': List of table names
            - 'tables_summary': Summary information for each table
        """
        if not self.test_connection():
            raise ConnectionError("Cannot connect to database")

        all_tables = self.list_all_tables()

        summary = {
            "database_info": self.get_database_info(),
            "table_count": len(all_tables),
            "tables": all_tables,
            "tables_summary": {},
        }

        # Get basic info for each table (without samples for performance)
        tables_info = self.get_all_tables_info(include_samples=False)

        for table_name, info in tables_info.items():
            summary["tables_summary"][table_name] = {
                "row_count": info.get("row_count", "Unknown"),
                "column_count": len(info.get("columns", [])),
                "columns": info.get("columns", []),
            }

        return summary

    def clear_cache(self) -> None:
        """
        Clear the internal cache of table information.

        Useful when database schema has changed.
        """
        self._table_info_cache.clear()


def create_data_manager(engine_config: Dict[str, Any]) -> DataManager:
    """
    Create a DataManager instance using engine configuration.

    Args:
        engine_config: Configuration dictionary for SQLAlchemy engine

    Returns:
        DataManager instance
    """
    db_manager = PDDataBaseManager(engine_config=engine_config)
    return DataManager(db_manager)
