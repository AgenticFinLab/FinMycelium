"""
Data Storage Manager Module:
This module extends MySQLDatabaseManager to handle dynamic table operations
while preserving the exact case of column names provided by the user.

Example Usage:

manager = DataStorageManager(
    table_name="RawData_PDF",
    required_columns=['RawDataID','Source', 'Location', 'Time', 'Copyright', 'Method', 'Tag'],
    column_types=['INT', 'VARCHAR(255)', 'VARCHAR(255)', 'DATETIME', 'VARCHAR(255)', 'VARCHAR(255)', 'VARCHAR(255)']
)

manager.create_table()
manager.import_csv_to_database("data.csv")

"""

import os
import pandas as pd
from typing import Optional, List, Tuple, Any
from finmy.collector.mysql_manager import MySQLDatabaseManager


class DataStorageManager(MySQLDatabaseManager):
    """
    A generic data storage manager that uses exact column names.
    
    This class allows you to:
      - Create a table with columns exactly matching `required_columns` and their specified types
      - Import CSV data where headers must match `required_columns` exactly (case-sensitive)
      - Perform basic CRUD-like operations on the table
    
    All database column names will be identical to the strings in `required_columns`.
    """

    def __init__(self, table_name: str, required_columns: List[str], column_types: List[str]):
        """
        Initialize the manager with a table name, exact column names, and their types.
        
        Args:
            table_name (str): Name of the database table (e.g., 'RawData_PDF').
            required_columns (List[str]): Exact column names to use in the table.
            column_types (List[str]): Corresponding SQL data types for each column.
        
        These must match the CSV headers exactly.
        """
        super().__init__()
        self.table_name = table_name
        self.required_columns = required_columns
        self.column_types = column_types

        # Validate that required_columns and column_types have the same length
        if len(self.required_columns) != len(self.column_types):
            raise ValueError("Length of required_columns and column_types must be the same.")

        # Optional: Validate column names for SQL safety (basic check)
        for col in self.required_columns:
            if not col.replace('_', '').replace('-', '').isalnum():
                raise ValueError(f"Potentially unsafe column name: '{col}'. "
                                 f"Only alphanumeric characters and underscores/hyphens allowed.")

    def create_table(self) -> bool:
        """
        Create the table with columns exactly matching `required_columns` and their specified types.
        
        The table includes:
          - `id` (primary key)
          - Columns from `required_columns` with their specified types
          - `created_at` and `updated_at` timestamps
        
        Returns:
            bool: True on success, False on failure.
        """
        # Build column definitions using original case and specified types
        column_defs = []
        for col, col_type in zip(self.required_columns, self.column_types):
            column_defs.append(f"`{col}` {col_type} NOT NULL")
        
        columns_sql = ",\n    ".join(column_defs)
        
        create_table_query = f"""
        CREATE TABLE IF NOT EXISTS `{self.table_name}` (
            `id` INT AUTO_INCREMENT PRIMARY KEY,
            {columns_sql},
            `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
        
        try:
            result = self.execute_query(create_table_query)
            if result is not None:
                print(f"Table '{self.table_name}' created or already exists.")
                return True
            else:
                print(f"Failed to create table '{self.table_name}'.")
                return False
        except Exception as e:
            print(f"Error creating table '{self.table_name}': {e}")
            return False

    def import_csv_to_database(self, csv_file_path: str) -> bool:
        """
        Import CSV data into the table using exact column name matching (case-sensitive).
        
        The CSV file must contain all columns in `required_columns` with identical casing.
        
        Args:
            csv_file_path (str): Path to the CSV file.
            
        Returns:
            bool: True if all records were inserted successfully, False otherwise.
        """
        try:
            if not os.path.exists(csv_file_path):
                print(f"Error: CSV file not found: {csv_file_path}")
                return False

            df = pd.read_csv(csv_file_path)

            # Check for exact match (case-sensitive) of required columns
            missing = [col for col in self.required_columns if col not in df.columns]
            if missing:
                print(f"Error: Missing required columns in CSV (case-sensitive): {missing}")
                return False

            # Build INSERT query with original column names
            columns_list = ", ".join([f"`{col}`" for col in self.required_columns])
            placeholders = ", ".join(["%s"] * len(self.required_columns))
            insert_query = f"INSERT INTO `{self.table_name}` ({columns_list}) VALUES ({placeholders})"

            records_to_insert: List[Tuple] = []
            for _, row in df.iterrows():
                record = []
                for col in self.required_columns:
                    value = row[col]
                    # Replace NaN/None with empty string to respect NOT NULL constraint
                    if pd.isna(value):
                        record.append('')
                    else:
                        record.append(str(value))
                records_to_insert.append(tuple(record))

            # Insert records
            success_count = 0
            total = len(records_to_insert)
            for record in records_to_insert:
                if self.execute_query(insert_query, record) is not None:
                    success_count += 1

            print(f"Import completed: {success_count}/{total} records inserted into '{self.table_name}'.")
            return success_count == total

        except pd.errors.EmptyDataError:
            print("Error: CSV file is empty.")
            return False
        except pd.errors.ParserError as e:
            print(f"CSV parsing error: {e}")
            return False
        except Exception as e:
            print(f"Unexpected error during import: {e}")
            return False

    def get_all_records(self) -> Optional[List[Tuple]]:
        """Fetch all records from the table."""
        query = f"SELECT * FROM `{self.table_name}` ORDER BY `id`"
        try:
            return self.execute_query(query)
        except Exception as e:
            print(f"Error fetching records: {e}")
            return None

    def count_records(self) -> Optional[int]:
        """Count total records in the table."""
        query = f"SELECT COUNT(*) FROM `{self.table_name}`"
        try:
            result = self.execute_query(query)
            return result[0][0] if result else None
        except Exception as e:
            print(f"Error counting records: {e}")
            return None

    def drop_table(self) -> bool:
        """
        Drop the table completely (removes table structure and all data).
        
        Returns:
            bool: True on success, False on failure.
        """
        query = f"DROP TABLE IF EXISTS `{self.table_name}`"
        try:
            if self.execute_query(query) is not None:
                print(f"Table '{self.table_name}' dropped successfully.")
                return True
            else:
                print(f"Failed to drop table '{self.table_name}'.")
                return False
        except Exception as e:
            print(f"Error dropping table: {e}")
            return False