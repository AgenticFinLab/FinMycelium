from finmy.db_manager import PDDataBaseManager

# Example usage
if __name__ == "__main__":
    # Example 1: Simple initialization (auto-loads from .env in root directory)
    # db_manager = PDDataBaseManager()

    # Example 2: Specify custom .env path
    # db_manager = PDDataBaseManager(env_path="/path/to/your/.env")

    # Example 3: Test connection
    db_manager = PDDataBaseManager()
    if db_manager.test_connection():
        print("Database connection successful!")
        print("Connection info:", db_manager.get_database_info())
    else:
        print("Database connection failed!")

    # Example 4: Use existing engine or config
    # engine_config = {
    #     'url': 'mysql+pymysql://user:pass@host:port/db',
    #     'echo': False
    # }
    # db_manager = PDDataBaseManager(engine_config=engine_config)

    print("PDDataBaseManager with .env support is ready!")
