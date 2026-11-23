"""Check the public database adapter with a disposable in-memory SQLite table."""
import pandas as pd

from finmy.db_manager import PDDataBaseManager


def main():
    db = PDDataBaseManager({"url": "sqlite://"})
    records = pd.DataFrame([{"source_id": "example", "location": "report/full.md"}])
    db.write_sql(records, "sources", if_exists="fail")
    print(db.read_sql_table("sources").to_string(index=False))


if __name__ == "__main__":
    main()
