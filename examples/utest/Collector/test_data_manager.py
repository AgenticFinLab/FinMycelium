from finmy.url_collector.MediaCollector.data_manager import create_data_manager_from_env


if __name__ == "__main__":
    dm = create_data_manager_from_env()

    if dm.test_connection():

        tables = dm.list_all_tables()
        print(f"tables: {tables}")

        for table in tables:
            print(f"Table: {table}")
            schema = dm.get_table_schema(table)
            print("Schema:\n", schema)

            sample = dm.get_table_sample(table, sample_size=3)
            print("samples:\n", sample)
            print("\n=======\n")

        summary = dm.summarize_database()
        print("summary:", summary)
