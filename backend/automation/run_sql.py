import pyodbc
import sys

SERVER   = "wp000047650"
DATABASE = "your_database"   # replace with your database name
USERNAME = "umr_macro_2026"
PASSWORD = "your_password"   # replace with your password

QUERY = "SELECT TOP 10 * FROM INFORMATION_SCHEMA.TABLES"


def main():
    connection_string = (
        f"DRIVER={{ODBC Driver 17 for SQL Server}};"
        f"SERVER={SERVER};"
        f"DATABASE={DATABASE};"
        f"UID={USERNAME};"
        f"PWD={PASSWORD};"
        "Encrypt=yes;"
        "TrustServerCertificate=yes;"
        "Connection Timeout=30;"
    )

    try:
        conn = pyodbc.connect(connection_string)
        print(f"Connected to {SERVER}/{DATABASE}")
    except pyodbc.Error as e:
        print(f"Connection failed: {e}")
        sys.exit(1)

    cursor = conn.cursor()
    cursor.execute(QUERY)

    columns = [col[0] for col in cursor.description]
    print(" | ".join(columns))
    print("-" * 60)
    for row in cursor.fetchall():
        print(" | ".join(str(v) for v in row))

    cursor.close()
    conn.close()


if __name__ == "__main__":
    main()
