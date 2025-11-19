"""
Data Storage Manager Module:
This module extends MySQLDatabaseManager to handle dynamic table operations
while preserving the exact case of column names provided by the user.

Example Usage:

manager = DataStorageManager(table_name="RawData_PDF")
manager.import_data_to_database("data.csv")  # This will automatically create table based on CSV headers
manager.import_data_to_database("data.json")  # This will automatically create table based on JSON keys
"""

import os
import re
import json
from typing import Optional, List, Tuple, Any, Dict, Union

import pandas as pd

from finmy.collector.mysql_manager import MySQLDatabaseManager



class DataStorageManager(MySQLDatabaseManager):
    """
    A generic data storage manager that uses exact column names.
    
    This class allows you to:
      - Automatically create a table based on CSV file headers or JSON keys and inferred types
      - Import CSV/JSON data where the table structure is dynamically determined
      - Perform basic CRUD-like operations on the table
    
    All database column names will be identical to the strings in CSV headers or JSON keys.
    """

    def __init__(self, table_name: str):
        """
        Initialize the manager with a table name.
        
        Args:
            table_name: Name of the database table (e.g., 'RawData_PDF').
        """
        super().__init__()
        self.table_name = table_name
        self.required_columns: Optional[List[str]] = None
        self.column_types: Optional[List[str]] = None

    def _infer_column_types(self, df: pd.DataFrame) -> List[str]:
        """
        Infer SQL column types based on pandas DataFrame column data types.
        
        Args:
            df: DataFrame to analyze
            
        Returns:
            List of corresponding SQL column types
        """
        column_types = []
        
        for col in df.columns:
            series = df[col]
            
            # Remove NaN values for type inference
            non_null_series = series.dropna()
            
            if non_null_series.empty:
                # If all values are null, default to VARCHAR(255)
                column_types.append('VARCHAR(255)')
                continue
            
            # Check if the column contains complex JSON objects (dicts or lists)
            if self._is_complex_json_column(series):
                column_types.append('JSON')
            # Check for numeric types
            elif pd.api.types.is_integer_dtype(series):
                column_types.append('INT')
            elif pd.api.types.is_float_dtype(series):
                column_types.append('DECIMAL(15,2)')
            # Check for datetime
            elif pd.api.types.is_datetime64_any_dtype(series) or self._is_datetime_column(non_null_series):
                column_types.append('DATETIME')
            # Check for boolean
            elif pd.api.types.is_bool_dtype(series):
                column_types.append('BOOLEAN')
            # Default to VARCHAR for string/object types
            else:
                # Determine appropriate VARCHAR length based on max string length
                max_length = 255  # default
                if len(non_null_series) > 0:
                    max_str_len = non_null_series.astype(str).str.len().max()
                    # Set reasonable limits
                    max_length = min(max(max_str_len, 50), 65535)  # Max for TEXT is 65535
                
                if max_length <= 255:
                    column_types.append('VARCHAR(255)')
                elif max_length <= 65535:
                    column_types.append('TEXT')
                else:
                    column_types.append('LONGTEXT')
        
        return column_types

    def _is_complex_json_column(self, series) -> bool:
        """
        Check if a series contains complex JSON objects (dicts or lists).
        
        Args:
            series: Pandas Series to check
            
        Returns:
            True if series contains complex JSON objects
        """
        # Sample up to 10 non-null values to check for complex JSON
        sample_size = min(10, len(series))
        sample = series.head(sample_size).dropna()
        
        for val in sample:
            # Check if the value is a dict or list
            if isinstance(val, (dict, list)):
                return True
            # Also check if it's a string representation of dict/list
            if isinstance(val, str):
                val = val.strip()
                if val.startswith(('{', '[')) and val.endswith(('}', ']')):
                    try:
                        json.loads(val)
                        return True
                    except:
                        continue
        return False

    def _is_datetime_column(self, series) -> bool:
        """
        Check if a series contains datetime-like values.
        
        Args:
            series: Pandas Series to check
            
        Returns:
            True if series appears to contain datetime values
        """
        try:
            # Sample up to 100 non-null values to check for datetime format
            sample_size = min(100, len(series))
            sample = series.head(sample_size)
            
            for val in sample:
                if pd.notna(val):
                    str_val = str(val)
                    # Check common datetime patterns
                    datetime_patterns = [
                        # YYYY-MM-DD HH:MM:SS
                        r'\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}',
                        # YYYY/MM/DD HH:MM:SS
                        r'\d{4}/\d{2}/\d{2}\s+\d{2}:\d{2}:\d{2}',
                        # MM/DD/YYYY HH:MM:SS
                        r'\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}:\d{2}',
                        # YYYY-MM-DD
                        r'\d{4}-\d{2}-\d{2}',
                        # YYYY/MM/DD
                        r'\d{4}/\d{2}/\d{2}',
                    ]
                    
                    for pattern in datetime_patterns:
                        if re.match(pattern, str_val):
                            return True
        except:
            pass
        
        return False

    def _load_data_from_file(self, file_path: str) -> pd.DataFrame:
        """
        Load data from CSV or JSON file into a pandas DataFrame.
        
        Args:
            file_path: Path to the data file
            
        Returns:
            DataFrame containing the loaded data
            
        Raises:
            ValueError: If file extension is not supported
            FileNotFoundError: If file does not exist
        """
        file_extension = os.path.splitext(file_path)[1].lower()
        
        if file_extension == '.csv':
            return pd.read_csv(file_path)
        elif file_extension == '.json':
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            # Ensure data is a list of dictionaries
            if not isinstance(data, list):
                raise ValueError("JSON file must contain an array of objects")
            
            # Validate that all items in the list are dictionaries
            for item in data:
                if not isinstance(item, dict):
                    raise ValueError("All items in JSON array must be objects")
            
            # Convert the list of dictionaries to DataFrame
            # For complex objects (dicts/lists), keep them as JSON strings
            df_data = []
            for item in data:
                row = {}
                for key, value in item.items():
                    if isinstance(value, (dict, list)):
                        # Convert complex objects to JSON string for storage
                        row[key] = json.dumps(value, ensure_ascii=False)
                    else:
                        row[key] = value
                df_data.append(row)
            
            return pd.DataFrame(df_data)
        else:
            raise ValueError(f"Unsupported file format: {file_extension}. Supported formats: .csv, .json")

    def create_table_from_file(self, file_path: str) -> bool:
        """
        Create table based on file structure (CSV headers or JSON keys).
        
        Args:
            file_path: Path to the CSV or JSON file.
            
        Returns:
            True on success, False on failure.
        """
        try:
            if not os.path.exists(file_path):
                print(f"Error: File not found: {file_path}")
                return False

            # Load data to get headers/keys and sample data for type inference
            df = self._load_data_from_file(file_path)
            
            # Set the required columns and types based on file
            self.required_columns = df.columns.tolist()
            self.column_types = self._infer_column_types(df)
            
            # Validate that required_columns and column_types have the same length
            if len(self.required_columns) != len(self.column_types):
                raise ValueError("Length of required_columns and column_types must be the same.")

            # Optional: Validate column names for SQL safety (basic check)
            for col in self.required_columns:
                if not col.replace('_', '').replace('-', '').isalnum():
                    raise ValueError(f"Potentially unsafe column name: '{col}'. "f"Only alphanumeric characters and underscores/hyphens allowed.")

            # Build column definitions using original case and inferred types
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
            
            result = self.execute_query(create_table_query)
            if result is not None:
                print(f"Table '{self.table_name}' created based on file structure with columns: {self.required_columns}")
                return True
            else:
                print(f"Failed to create table '{self.table_name}'.")
                return False
                
        except Exception as e:
            print(f"Error creating table from file: {e}")
            return False

    def import_data_to_database(self, file_path: str, auto_create_table: bool = True) -> bool:
        """
        Import CSV or JSON data into the table, optionally creating the table first based on file structure.
        
        Args:
            file_path: Path to the CSV or JSON file.
            auto_create_table: Whether to automatically create table based on file if it doesn't exist.
            
        Returns:
            True if all records were inserted successfully, False otherwise.
        """
        try:
            if not os.path.exists(file_path):
                print(f"Error: File not found: {file_path}")
                return False

            df = self._load_data_from_file(file_path)

            # If table doesn't exist and auto_create_table is True, create it first
            if auto_create_table and self.required_columns is None:
                if not self.create_table_from_file(file_path):
                    print("Failed to create table from file, aborting import.")
                    return False
            elif self.required_columns is None:
                # If auto_create_table is False and we don't have column info, try to create table
                if not self.create_table_from_file(file_path):
                    print("Failed to create table from file, aborting import.")
                    return False

            # Check for exact match (case-sensitive) of required columns
            missing = [col for col in self.required_columns if col not in df.columns]
            if missing:
                print(f"Error: Missing required columns in file (case-sensitive): {missing}")
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
                        # For JSON type columns, ensure the value is properly formatted
                        if self.column_types[self.required_columns.index(col)] == 'JSON':
                            # If the value is already a JSON string, use it directly
                            # Otherwise, convert to JSON string
                            if isinstance(value, (dict, list)):
                                record.append(json.dumps(value, ensure_ascii=False))
                            else:
                                record.append(str(value))
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
            print("Error: File is empty.")
            return False
        except pd.errors.ParserError as e:
            print(f"File parsing error: {e}")
            return False
        except ValueError as e:
            print(f"Value error: {e}")
            return False
        except Exception as e:
            print(f"Unexpected error during import: {e}")
            return False

    def create_table(self) -> bool:
        """
        Create the table with the current required_columns and column_types.
        
        This method can be used if you've manually set required_columns and column_types.
        
        Returns:
            True on success, False on failure.
        """
        if self.required_columns is None or self.column_types is None:
            print("Error: required_columns and column_types must be set before creating table.")
            return False

        # Validate that required_columns and column_types have the same length
        if len(self.required_columns) != len(self.column_types):
            raise ValueError("Length of required_columns and column_types must be the same.")

        # Optional: Validate column names for SQL safety (basic check)
        for col in self.required_columns:
            if not col.replace('_', '').replace('-', '').isalnum():
                raise ValueError(f"Potentially unsafe column name: '{col}'. "
                                 f"Only alphanumeric characters and underscores/hyphens allowed.")

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
            True on success, False on failure.
        """
        query = f"DROP TABLE IF EXISTS `{self.table_name}`"
        try:
            if self.execute_query(query) is not None:
                print(f"Table '{self.table_name}' dropped successfully.")
                # Reset column info when table is dropped
                self.required_columns = None
                self.column_types = None
                return True
            else:
                print(f"Failed to drop table '{self.table_name}'.")
                return False
        except Exception as e:
            print(f"Error dropping table: {e}")
            return False

    def get_table_info(self) -> Tuple[Optional[List[str]], Optional[List[str]]]:
        """
        Get current table column names and types.
        
        Returns:
            Tuple of (required_columns, column_types) or (None, None) if not set.
        """
        return self.required_columns, self.column_types