"""Database layer for the Smart Parking Management System.

Two engines are supported, chosen with the DB_ENGINE environment variable:

  mysql  (default) - the real project database built from sql/mysql/*.sql.
                     Business logic runs inside MySQL: triggers do the
                     occupancy and billing, stored procedures do entry/exit.
  sqlite           - zero-setup demo copy (sql/sqlite/schema.sql). Same
                     tables, data, views and triggers; the three stored
                     procedures are mirrored in Python below.

All SQL in the app is written with %s placeholders and works on both.
"""
import os
import sqlite3
from datetime import date, datetime, timedelta
from decimal import Decimal

from flask import g

ENGINE = os.environ.get("DB_ENGINE", "mysql").lower()
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SQLITE_PATH = os.environ.get("SQLITE_PATH", os.path.join(BASE_DIR, "smart_parking.db"))

MYSQL_CONFIG = dict(
    host=os.environ.get("MYSQL_HOST", "localhost"),
    port=int(os.environ.get("MYSQL_PORT", "3306")),
    user=os.environ.get("MYSQL_USER", "root"),
    password=os.environ.get("MYSQL_PASSWORD", ""),
    database=os.environ.get("MYSQL_DB", "smart_parking_system"),
)


class DBError(Exception):
    """A business-rule error raised by a trigger, procedure or constraint."""


# --------------------------------------------------------------------------
# connections
# --------------------------------------------------------------------------
def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _sqlite_occupancy(conn):
    def fn(lot_id):
        # occupied = slots with a car parked now (calculated, same as MySQL)
        total = conn.execute("SELECT COUNT(*) FROM parking_slot WHERE lot_id = ?", (lot_id,)).fetchone()[0]
        occ = conn.execute("SELECT COUNT(*) FROM parking_session s JOIN parking_slot sl ON sl.slot_id = s.slot_id "
                           "WHERE sl.lot_id = ? AND s.exit_time IS NULL", (lot_id,)).fetchone()[0]
        return round((occ or 0) * 100.0 / total, 2) if total else None
    return fn


def init_sqlite(path=SQLITE_PATH, force=False):
    """Create the SQLite demo database from sql/sqlite/schema.sql."""
    if force and os.path.exists(path):
        os.remove(path)
    if os.path.exists(path):
        return
    conn = sqlite3.connect(path)
    with open(os.path.join(BASE_DIR, "sql", "sqlite", "schema.sql"), encoding="utf-8") as f:
        conn.executescript(f.read())
    conn.commit()
    conn.close()


def get_conn():
    if "db" in g:
        return g.db
    if ENGINE == "sqlite":
        init_sqlite()
        conn = sqlite3.connect(SQLITE_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        # Same names as in MySQL so every query in the app is portable.
        conn.create_function("NOW", 0, _now)
        conn.create_function("fn_occupancy_percent", 1, _sqlite_occupancy(conn))
    else:
        import pymysql
        try:
            conn = pymysql.connect(**MYSQL_CONFIG, autocommit=True,
                                   cursorclass=pymysql.cursors.DictCursor)
        except pymysql.err.OperationalError as e:
            raise DBError("Could not connect to MySQL at %s:%s as '%s' (%s). Check that MySQL is running, "
                          "that you ran setup_db.py, and that MYSQL_PASSWORD is set — or start the app "
                          "with DB_ENGINE=sqlite for the demo database."
                          % (MYSQL_CONFIG["host"], MYSQL_CONFIG["port"], MYSQL_CONFIG["user"], e.args[-1]))
    g.db = conn
    return conn


def close_conn(_exc=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def _sql(sql):
    return sql.replace("%s", "?") if ENGINE == "sqlite" else sql


def _clean(row):
    out = {}
    for k, v in dict(row).items():
        if isinstance(v, Decimal):
            v = float(v)
        elif isinstance(v, datetime):
            v = v.strftime("%Y-%m-%d %H:%M:%S")
        elif isinstance(v, date):
            v = v.isoformat()
        elif isinstance(v, bytes):
            v = v.decode()
        out[k] = v
    return out


def _wrap(exc):
    """Turn driver errors into a readable DBError message."""
    unique_rules = {   # unique keys on generated columns -> plain-language rule
        "active_slot": "Slot is already occupied",
        "uq_one_car_per_slot": "Slot is already occupied",
        "active_vehicle": "This vehicle is already parked",
        "uq_one_slot_per_car": "This vehicle is already parked",
        "confirmed_slot": "Slot already has a confirmed booking",
        "uq_one_confirmed_booking_per_slot": "Slot already has a confirmed booking",
    }
    if ENGINE == "sqlite":
        msg = str(exc)
        if msg.startswith("UNIQUE constraint failed: "):
            col = msg.split(": ", 1)[1]
            for key, text in unique_rules.items():
                if key in col:
                    return DBError(text)
            return DBError("Duplicate value: " + col + " already exists")
        if msg.startswith("FOREIGN KEY constraint failed"):
            return DBError("Refused: other records depend on this one (history is protected)")
        return DBError(msg.replace("CHECK constraint failed: ", "Constraint failed: "))
    args = getattr(exc, "args", ())
    if len(args) >= 2:
        code, msg = args[0], args[1]
        if code == 1062:
            for key, text in unique_rules.items():
                if key in msg:
                    return DBError(text)
            return DBError("Duplicate value: " + msg.split("'")[1] + " already exists")
        if code in (1451, 1452):
            return DBError("Refused: other records depend on this one (history is protected)"
                           if code == 1451 else "Refused: the linked record does not exist")
        if code == 3819:
            return DBError("Constraint failed: " + msg)
        return DBError(msg)
    return DBError(str(exc))


def _driver_errors():
    if ENGINE == "sqlite":
        return (sqlite3.IntegrityError, sqlite3.OperationalError)
    import pymysql
    return (pymysql.err.OperationalError, pymysql.err.IntegrityError,
            pymysql.err.InternalError, pymysql.err.DataError)


# --------------------------------------------------------------------------
# public helpers
# --------------------------------------------------------------------------
def query(sql, params=(), one=False):
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(_sql(sql), params) if params else cur.execute(_sql(sql))
        rows = [_clean(r) for r in cur.fetchall()]
    except _driver_errors() as e:
        raise _wrap(e)
    return (rows[0] if rows else None) if one else rows


def query_with_columns(sql):
    """Run a read-only report query; return (columns, rows)."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(_sql(sql))
    except _driver_errors() as e:
        raise _wrap(e)
    cols = [d[0] for d in cur.description]
    return cols, [_clean(r) for r in cur.fetchall()]


def execute(sql, params=()):
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(_sql(sql), params) if params else cur.execute(_sql(sql))
        if ENGINE == "sqlite":
            conn.commit()
        return cur.lastrowid
    except _driver_errors() as e:
        if ENGINE == "sqlite":
            conn.rollback()
        raise _wrap(e)


# --------------------------------------------------------------------------
# stored procedures
# --------------------------------------------------------------------------
def _call_mysql(proc, args):
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.callproc(proc, args)
        result = cur.fetchone()
        while cur.nextset():
            pass
        return _clean(result) if result else None
    except _driver_errors() as e:
        raise _wrap(e)


def vehicle_entry(vehicle_id, lot_id):
    """CALL sp_vehicle_entry -> {'session_id', 'slot_id'}"""
    if ENGINE != "sqlite":
        return _call_mysql("sp_vehicle_entry", (vehicle_id, lot_id))
    v = query("SELECT vehicle_type FROM vehicle WHERE vehicle_id=%s", (vehicle_id,), one=True)
    if not v:
        raise DBError("Vehicle not found")
    if query("SELECT 1 FROM parking_session WHERE active_vehicle=%s", (vehicle_id,), one=True):
        raise DBError("This vehicle is already parked")
    slot = query("SELECT slot_id FROM vw_slot_status WHERE lot_id=%s AND slot_type=%s "
                 "AND status='Available' ORDER BY floor_number, slot_number LIMIT 1",
                 (lot_id, v["vehicle_type"]), one=True)
    if not slot:
        raise DBError("No available slot for this vehicle type")
    sid = execute("INSERT INTO parking_session (vehicle_id, slot_id, entry_time) "
                  "VALUES (%s, %s, %s)", (vehicle_id, slot["slot_id"], _now()))
    return {"session_id": sid, "slot_id": slot["slot_id"]}


def vehicle_exit(session_id):
    """CALL sp_vehicle_exit -> billing is done by the exit trigger."""
    if ENGINE != "sqlite":
        _call_mysql("sp_vehicle_exit", (session_id,))
        return
    s = query("SELECT session_status FROM parking_session WHERE session_id=%s", (session_id,), one=True)
    if not s:
        raise DBError("Session not found")
    if s["session_status"] != "Active":
        raise DBError("Session is already completed")
    execute("UPDATE parking_session SET exit_time=%s WHERE session_id=%s", (_now(), session_id))


def booking_checkin(booking_id):
    """CALL sp_booking_checkin -> {'session_id', 'slot_id'}"""
    if ENGINE != "sqlite":
        return _call_mysql("sp_booking_checkin", (booking_id,))
    b = query("SELECT booking_status, vehicle_id, slot_id FROM booking WHERE booking_id=%s",
              (booking_id,), one=True)
    if not b:
        raise DBError("Booking not found")
    if b["booking_status"] != "Confirmed":
        raise DBError("Only confirmed bookings can be checked in")
    # the remaining checks (already parked, slot free, maintenance) are done
    # by trg_before_session_insert, exactly as in MySQL
    sid = execute("INSERT INTO parking_session (booking_id, vehicle_id, slot_id, entry_time) "
                  "VALUES (%s, %s, %s, %s)",
                  (booking_id, b["vehicle_id"], b["slot_id"], _now()))
    return {"session_id": sid, "slot_id": b["slot_id"]}


def engine_label():
    if ENGINE == "sqlite":
        return "SQLite demo"
    return "MySQL · " + MYSQL_CONFIG["database"]
