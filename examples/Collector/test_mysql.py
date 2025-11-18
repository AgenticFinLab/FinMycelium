"""
MySQL Database Operations Module
This module provides a comprehensive interface for MySQL database operations
using environment variables for secure credential management.
"""

import mysql.connector
from mysql.connector import Error
from dotenv import load_dotenv
import os

# Load environment variables from .env file
# The .env file should contain database connection parameters and should not be committed to version control
load_dotenv()


class MySQLDatabaseManager:
    """
    A class to manage MySQL database operations including connection, query execution,
    and basic CRUD operations.

    This class uses environment variables for all sensitive information to ensure
    security and configuration flexibility.
    """

    def __init__(self):
        """
        Initialize the database manager with configuration from environment variables.

        Raises:
            ValueError: If required environment variables are missing
        """
        # Database server hostname or IP address
        self.host = os.getenv("DB_HOST")
        # Database port number, defaults to 3306 if not specified
        self.port = int(os.getenv("DB_PORT", 3306))
        # Name of the database to connect to
        self.database = os.getenv("DB_NAME")
        # Username for database authentication
        self.user = os.getenv("DB_USER")
        # Password for database authentication
        self.password = os.getenv("DB_PASSWORD")
        # Character encoding for the connection, defaults to utf8mb4 for full Unicode support
        self.charset = os.getenv("DB_CHARSET", "utf8mb4")
        # Database connection object, initialized as None
        self.connection = None

        # Validate that all required configuration parameters are present
        self._validate_config()

    def _validate_config(self):
        """
        Validate that all required environment variables are properly set.

        This method checks for the presence of essential database connection
        parameters and raises an exception if any are missing.

        Raises:
            ValueError: With detailed message about which variables are missing
        """
        # List of required environment variable names
        required_vars = ["DB_HOST", "DB_NAME", "DB_USER", "DB_PASSWORD"]
        # Find which required variables are not set
        missing_vars = [var for var in required_vars if not os.getenv(var)]

        # If any required variables are missing, raise an exception
        if missing_vars:
            raise ValueError(
                f"Missing required environment variables: {', '.join(missing_vars)}"
            )

    def connect(self):
        """
        Establish a connection to the MySQL database.

        Returns:
            bool: True if connection was successful, False otherwise

        Note:
            This method handles connection exceptions and provides
            appropriate error messages for troubleshooting.
        """
        try:
            # Create database connection using mysql.connector
            self.connection = mysql.connector.connect(
                host=self.host,
                port=self.port,
                database=self.database,
                user=self.user,
                password=self.password,
                charset=self.charset,
            )

            # Verify the connection is active
            if self.connection.is_connected():
                print(f"Connected to MySQL database: {self.database}")
                return True

        except Error as e:
            # Handle connection errors and provide diagnostic information
            print(f"Error connecting to MySQL: {e}")
            return False

    def disconnect(self):
        """
        Close the database connection if it exists and is active.

        This method ensures proper cleanup of database resources
        and should be called when database operations are complete.
        """
        if self.connection and self.connection.is_connected():
            self.connection.close()
            print("Database connection closed")

    def execute_query(self, query, params=None):
        """
        Execute a SQL query with optional parameters.

        Args:
            query (str): The SQL query to execute
            params (tuple, optional): Parameters for parameterized queries

        Returns:
            list: For SELECT queries, returns fetched results
            int: For INSERT/UPDATE/DELETE queries, returns number of affected rows
            None: If an error occurs during query execution

        Note:
            This method automatically handles transaction commit for write operations
            and rollback in case of errors.
        """
        try:
            # Create a cursor object for executing queries
            cursor = self.connection.cursor()
            # Execute the query with provided parameters
            cursor.execute(query, params or ())

            # Handle SELECT queries by fetching all results
            if query.strip().upper().startswith("SELECT"):
                result = cursor.fetchall()
                return result
            else:
                # For write operations, commit the transaction
                self.connection.commit()
                print(f"Query executed. Affected rows: {cursor.rowcount}")
                return cursor.rowcount

        except Error as e:
            # Rollback transaction on error and provide error details
            print(f"Error executing query: {e}")
            self.connection.rollback()
            return None
        finally:
            # Ensure cursor is closed to free resources
            if "cursor" in locals():
                cursor.close()

    def create_sample_table(self):
        """
        Create a sample table for financial records if it doesn't exist.

        This method demonstrates table creation with common data types
        and constraints including auto-increment primary key, timestamps,
        and proper character set configuration.
        """
        create_table_query = """
        CREATE TABLE IF NOT EXISTS financial_records (
            id INT AUTO_INCREMENT PRIMARY KEY,
            company_name VARCHAR(255) NOT NULL,
            revenue DECIMAL(15,2),
            profit DECIMAL(15,2),
            record_date DATE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
        self.execute_query(create_table_query)
        print("Table 'financial_records' created or already exists")

    def insert_sample_data(self):
        """
        Insert sample data into the financial_records table.

        This method demonstrates batch insertion of multiple records
        using parameterized queries to prevent SQL injection.
        """
        insert_query = """
        INSERT INTO financial_records (company_name, revenue, profit, record_date)
        VALUES (%s, %s, %s, %s)
        """

        # Sample data representing financial records
        sample_data = [
            ("Sijia Inc", 1500000.50, 350000.75, "2025-11-18"),
            ("Yuxuan Ltd", 890000.25, 210000.30, "2025-11-18"),
            ("Yuqun Corp", 1200000.00, 280000.50, "2025-11-18"),
        ]

        # Insert each record individually
        for data in sample_data:
            self.execute_query(insert_query, data)

        print("Sample data inserted successfully")

    def fetch_all_data(self):
        """
        Retrieve and display all records from the financial_records table.

        Returns:
            list: All records from the financial_records table, or None if error occurs

        Note:
            Results are ordered by ID to ensure consistent output ordering.
        """
        select_query = "SELECT * FROM financial_records ORDER BY id"
        results = self.execute_query(select_query)

        # Display results if any records were found
        if results:
            print("All Financial Records:")
            for row in results:
                print(
                    f"ID: {row[0]}, Company: {row[1]}, Revenue: {row[2]}, Profit: {row[3]}, Date: {row[4]}"
                )

        return results

    def update_record(self, record_id, new_revenue, new_profit):
        """
        Update revenue and profit for a specific record.

        Args:
            record_id (int): The ID of the record to update
            new_revenue (float): New revenue value
            new_profit (float): New profit value

        Note:
            This method demonstrates updating specific fields in a record
            and provides feedback on whether the update was successful.
        """
        update_query = """
        UPDATE financial_records 
        SET revenue = %s, profit = %s 
        WHERE id = %s
        """

        affected_rows = self.execute_query(
            update_query, (new_revenue, new_profit, record_id)
        )

        if affected_rows:
            print(f"Record {record_id} updated successfully")
        else:
            print(f"No record found with ID {record_id}")

    def delete_record(self, record_id):
        """
        Delete a specific record from the financial_records table.

        Args:
            record_id (int): The ID of the record to delete

        Note:
            This method provides feedback on whether the deletion was successful
            or if no record was found with the specified ID.
        """
        delete_query = "DELETE FROM financial_records WHERE id = %s"

        affected_rows = self.execute_query(delete_query, (record_id,))

        if affected_rows:
            print(f"Record {record_id} deleted successfully")
        else:
            print(f"No record found with ID {record_id}")


def main():
    """
    Main function demonstrating the usage of MySQLDatabaseManager class.

    This function showcases a complete workflow including:
    - Database connection
    - Table creation
    - Data insertion
    - Data retrieval
    - Data updating
    - Proper resource cleanup

    Exception handling ensures graceful error recovery and resource cleanup.
    """
    try:
        # Initialize database manager
        db_manager = MySQLDatabaseManager()

        # Establish database connection
        if db_manager.connect():
            # Create sample table
            db_manager.create_sample_table()
            # Insert sample data
            db_manager.insert_sample_data()
            # Display all records
            db_manager.fetch_all_data()

            # Demonstrate update operation
            db_manager.update_record(1, 1600000.00, 400000.00)
            # Display updated records
            db_manager.fetch_all_data()

    except Exception as e:
        # Handle any unexpected exceptions
        print(f"An error occurred: {e}")

    finally:
        # Ensure database connection is properly closed
        if "db_manager" in locals():
            db_manager.disconnect()


# Entry point of the script
if __name__ == "__main__":
    main()
