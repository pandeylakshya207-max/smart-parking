"""Build the database for the Smart Parking Management System.

    python setup_db.py            # MySQL: runs sql/mysql/01..04 in order
    python setup_db.py --sqlite   # SQLite demo: (re)creates smart_parking.db

MySQL connection settings come from the same environment variables the app
uses (MYSQL_HOST, MYSQL_PORT, MYSQL_USER, MYSQL_PASSWORD). If MYSQL_PASSWORD
is not set you will be asked for it.

WARNING: 01_schema.sql starts with DROP DATABASE IF EXISTS smart_parking_system,
so running this resets all data to the report's sample data.
"""
import getpass
import glob
import os
import re
import sys

BASE = os.path.dirname(os.path.abspath(__file__))


def split_mysql_script(text):
    """Split a .sql file into statements, honouring DELIMITER lines
    (the mysql CLI understands DELIMITER, drivers like PyMySQL do not)."""
    statements, buf, delim = [], [], ";"
    for line in text.splitlines():
        m = re.match(r"^\s*DELIMITER\s+(\S+)\s*$", line, re.I)
        if m:
            delim = m.group(1)
            continue
        if not buf and (line.strip().startswith("--") or not line.strip()):
            continue
        buf.append(line)
        if line.rstrip().endswith(delim):
            stmt = "\n".join(buf).rstrip()
            stmt = stmt[: -len(delim)].strip()
            if stmt:
                statements.append(stmt)
            buf = []
    tail = "\n".join(buf).strip()
    if tail:
        statements.append(tail)
    return statements


def setup_mysql():
    import pymysql
    password = os.environ.get("MYSQL_PASSWORD")
    if password is None:
        password = getpass.getpass("MySQL password for user '%s': " % os.environ.get("MYSQL_USER", "root"))
    conn = pymysql.connect(
        host=os.environ.get("MYSQL_HOST", "localhost"),
        port=int(os.environ.get("MYSQL_PORT", "3306")),
        user=os.environ.get("MYSQL_USER", "root"),
        password=password,
        autocommit=True,
    )
    cur = conn.cursor()
    for path in sorted(glob.glob(os.path.join(BASE, "sql", "mysql", "*.sql"))):
        with open(path, encoding="utf-8") as f:
            stmts = split_mysql_script(f.read())
        for s in stmts:
            try:
                cur.execute(s)
            except Exception as e:
                print("\nFAILED in %s:\n%s\n-> %s" % (os.path.basename(path), s[:300], e))
                sys.exit(1)
        print("ok  %-38s %3d statements" % (os.path.basename(path), len(stmts)))
    cur.execute("USE smart_parking_system")
    cur.execute("SELECT COUNT(*) FROM parking_slot")
    print("\nDatabase smart_parking_system is ready (%d slots)." % cur.fetchone()[0])
    conn.close()


def setup_sqlite():
    os.environ["DB_ENGINE"] = "sqlite"
    import db
    db.init_sqlite(force=True)
    print("SQLite demo database created at", db.SQLITE_PATH)


if __name__ == "__main__":
    if "--sqlite" in sys.argv:
        setup_sqlite()
    else:
        setup_mysql()
