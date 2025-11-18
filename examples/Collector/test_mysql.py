"""
MySQL Database Manager Example Usage
This script demonstrates how to use the MySQLDatabaseManager class
for various database operations.
"""

from finmy.collector.mysql_manager import MySQLDatabaseManager


def demonstrate_basic_operations():
    """
    Demonstrate basic database operations including connection,
    table creation, data insertion, and retrieval.
    """
    print("=== Basic Database Operations Demo ===")
    
    # Initialize database manager
    db_manager = MySQLDatabaseManager()

    try:
        # Establish database connection
        if db_manager.connect():
            # Create sample table
            db_manager.create_sample_table()
            
            # Insert sample data
            db_manager.insert_sample_data()
            
            # Display all records
            print("\n--- Initial Data ---")
            db_manager.fetch_all_data()

            # Demonstrate update operation
            print("\n--- Updating Record ---")
            db_manager.update_record(1, 1600000.00, 400000.00)
            
            # Display updated records
            print("\n--- After Update ---")
            db_manager.fetch_all_data()

            # Demonstrate delete operation
            print("\n--- Deleting Record ---")
            db_manager.delete_record(2)
            
            # Display records after deletion
            print("\n--- After Deletion ---")
            db_manager.fetch_all_data()

    except Exception as e:
        print(f"An error occurred: {e}")

    finally:
        # Ensure database connection is properly closed
        db_manager.disconnect()


def demonstrate_custom_queries():
    """
    Demonstrate custom query execution with parameters.
    """
    print("\n=== Custom Query Demo ===")
    
    db_manager = MySQLDatabaseManager()

    try:
        if db_manager.connect():
            # Execute a custom SELECT query
            select_query = "SELECT company_name, revenue FROM financial_records WHERE revenue > %s"
            high_revenue_companies = db_manager.execute_query(select_query, (1000000,))
            
            if high_revenue_companies:
                print("Companies with revenue > 1,000,000:")
                for company, revenue in high_revenue_companies:
                    print(f"  - {company}: ${revenue:,.2f}")

            # Execute a custom UPDATE query
            update_query = "UPDATE financial_records SET profit = %s WHERE company_name = %s"
            affected = db_manager.execute_query(update_query, (300000.00, "Sijia Inc"))
            print(f"\nUpdated {affected} record(s)")

            # Show the updated data
            print("\n--- Updated Data ---")
            db_manager.fetch_all_data()

    except Exception as e:
        print(f"An error occurred: {e}")

    finally:
        db_manager.disconnect()


def main():
    """
    Main function demonstrating various usage scenarios of MySQLDatabaseManager.
    """
    print("MySQL Database Manager Usage Examples")
    print("=" * 50)
    
    # Demonstrate basic operations
    demonstrate_basic_operations()
    
    # Demonstrate custom queries
    demonstrate_custom_queries()


if __name__ == "__main__":
    main()