"""
Parser Information Data Import Script
This script provides command-line functionality to import parser information
from a CSV file into the database using the DataStorageManager.
"""

import os
import sys
import argparse
from typing import NoReturn

from finmy.collector.db_storage_manager import DataStorageManager

def parse_arguments() -> argparse.Namespace:
    """
    Parse command-line arguments for the script.
    
    This function defines and parses the command-line arguments
    that control the behavior of the data import process.
    
    Returns:
        argparse.Namespace: Parsed command-line arguments
    """
    parser = argparse.ArgumentParser(
        description="Import parser information data from CSV to database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
        Examples:
        %(prog)s --csv-file /path/to/parser_information.csv
        %(prog)s --csv-file /path/to/parser_information.csv --create-table
        %(prog)s --csv-file /path/to/parser_information.csv --clear-table
        %(prog)s --csv-file /path/to/parser_information.csv --delete-table
        """
    )
    
    parser.add_argument(
        '--csv-file',
        type=str,
        default="output/parser_information.csv",
        help='Path to the CSV file containing parser information data'
    )
    
    parser.add_argument(
        '--table-name',
        type=str,
        default="RawData_PDF",
        help='Name of the database table to use'
    )

    parser.add_argument(
        '--required-columns',
        type=list[str],
        default=['RawDataID','Source', 'Location', 'Time', 'Copyright', 'Method', 'Tag'],
        help='Comma-separated list of required columns in the CSV file'
    )

    parser.add_argument(
        '--column-types',
        type=list[str],
        default=['INT', 'VARCHAR(255)', 'VARCHAR(255)', 'DATETIME', 'VARCHAR(255)', 'VARCHAR(255)', 'VARCHAR(255)'],
        help='Comma-separated list of column types for the required columns'
    )

    parser.add_argument(
        '--create-table',
        default=True,
        help='Create the table before importing data'
    )
        
    parser.add_argument(
        '--delete-table',
        default=True,
        help='Delete the existing table and recreate it before importing data'
    )
    
    parser.add_argument(
        '--show-stats',
        default=True,
        help='Show statistics about the imported data after completion'
    )
    
    return parser.parse_args()


def validate_csv_file(csv_file_path: str) -> bool:
    """
    Validate that the specified CSV file exists and is accessible.
    
    This function checks if the provided CSV file path is valid
    and the file can be read.
    
    Args:
        csv_file_path (str): Path to the CSV file to validate
        
    Returns:
        bool: True if the file is valid, False otherwise
    """
    if not os.path.exists(csv_file_path):
        print(f"Error: CSV file does not exist at '{csv_file_path}'")
        return False
    
    if not os.path.isfile(csv_file_path):
        print(f"Error: '{csv_file_path}' is not a file")
        return False
    
    if not os.access(csv_file_path, os.R_OK):
        print(f"Error: Cannot read CSV file at '{csv_file_path}' - check permissions")
        return False
    
    return True


def show_import_statistics(db_manager: DataStorageManager) -> None:
    """
    Display statistics about the data in the database.
    
    This function retrieves and displays various statistics about the
    data stored in the table.
    
    Args:
        db_manager (DataStorageManager): Instance of DataStorageManager
    """
    print("\n--- Import Statistics ---")
    
    # Count total records
    total_records = db_manager.count_records()
    if total_records is not None:
        print(f"Total records in database: {total_records}")
    else:
        print("Could not retrieve total record count")
    
    # Show sample records
    sample_records = db_manager.get_all_records()
    if sample_records:
        print(f"Sample records (first 5):")
        for i, record in enumerate(sample_records[:5]):
            # Skip ID column in display
            print(f"  Record {record[0]}: {record[1:]}")  
        
        if len(sample_records) > 5:
            print(f"  ... and {len(sample_records) - 5} more records")
    else:
        print("No records found in the database")


def main() -> NoReturn:
    """
    Main function to execute the data import process.
    
    This function orchestrates the entire data import process including
    argument parsing, database connection, table creation, data import,
    and optional statistics display.
    """
    # Parse command-line arguments
    args = parse_arguments()
    
    # Validate CSV file
    if not validate_csv_file(args.csv_file):
        sys.exit(1)
        
    # Initialize database manager
    db_manager = DataStorageManager(
        table_name=args.table_name,
        required_columns=args.required_columns,
        column_types=args.column_types
    )
    
    try:
        # Connect to the database
        print("Connecting to database...")
        if not db_manager.connect():
            print("Failed to connect to the database. Please check your configuration.")
            sys.exit(1)
        
        # Delete table if requested (this will also clear any existing data)
        if args.delete_table:
            print(f"Dropping {args.table_name} table...")
            if not db_manager.drop_table():
                print(f"Failed to drop the {args.table_name} table.")
                sys.exit(1)
        
        # Create table if requested
        if args.create_table:
            print(f"Creating {args.table_name} table...")
            if not db_manager.create_table():
                print(f"Failed to create the {args.table_name} table.")
                sys.exit(1)
        
        # Import data from CSV
        print(f"Importing data from '{args.csv_file}'...")
        if not db_manager.import_csv_to_database(args.csv_file):
            print("Failed to import data from CSV file.")
            sys.exit(1)
        
        # Show statistics if requested
        if args.show_stats:
            show_import_statistics(db_manager)
        
        print("Data import completed successfully!")
        
    except KeyboardInterrupt:
        print("\nOperation interrupted by user.")
        sys.exit(1)
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        sys.exit(1)
    finally:
        # Ensure database connection is closed
        print("Closing database connection...")
        db_manager.disconnect()


if __name__ == "__main__":
    main()