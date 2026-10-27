# Smart Parking Management System — working model

A web application on top of the MySQL database designed in the DBMS project report.
All the parking logic (slot occupancy, billing, freeing slots, booking rules) runs
**inside the database** as triggers and stored procedures; the web app just calls them
and shows the result.

| Screen | What it does | Database objects used |
| --- | --- | --- |
| Dashboard | Live slot map of every lot, occupancy bars, who is parked now, revenue | `vw_active_sessions`, `vw_slot_availability`, `fn_occupancy_percent()` |
| Vehicle entry | Type a plate, pick a lot → first free slot of the right type is allocated | `sp_vehicle_entry`, `trg_after_session_insert` |
| Sessions & billing | Exit a vehicle → hours and bill computed → collect payment | `sp_vehicle_exit`, `trg_before_session_update`, `trg_after_session_exit`, `payment` |
| Bookings | Reserve a slot, check in against the booking, or cancel | `trg_before_booking_insert`, `trg_after_booking_insert`, `trg_after_booking_cancel`, `sp_booking_checkin` |
| Customers | Register customers and vehicles (passwords stored hashed), parking history | `customer`, `vehicle` |
| Lots & rates | Slot map, maintenance on/off, add slots, edit rate card, staff | `parking_slot`, `parking_rate`, `staff`, `vw_revenue_per_lot` |
| SQL reports | The 17 queries from Section 5 of the report, run live | joins, subqueries, GROUP BY/HAVING, window function, views |

---

## Option A — run with MySQL (the real project)

You need **MySQL 8.0+** (or XAMPP/MariaDB 10.4+) and **Python 3.9+**.

**1. Install the Python packages** (inside the project folder):

```
pip install -r requirements.txt
```

**2. Build the database.** This runs the four scripts in `sql/mysql/` in order.
It asks for your MySQL root password.

```
python setup_db.py
```

> It starts with `DROP DATABASE IF EXISTS smart_parking_system`, so running it again
> resets everything to the report's sample data. Handy before a demo.

**3. Start the app** — set your MySQL password first:

macOS / Linux:
```
export MYSQL_PASSWORD='your_password'
python app.py
```

Windows (PowerShell):
```
$env:MYSQL_PASSWORD="your_password"
python app.py
```

**4. Open** http://127.0.0.1:5000

Other settings if you need them: `MYSQL_HOST` (default `localhost`), `MYSQL_PORT` (`3306`),
`MYSQL_USER` (`root`), `MYSQL_DB` (`smart_parking_system`).

You can also run the four `.sql` files by hand in MySQL Workbench (File → Open SQL Script,
then the lightning bolt), in the order 01 → 04, instead of `setup_db.py`.

## Option B — zero-setup demo (no MySQL needed)

Same app, same tables, data, views and trigger behaviour, on SQLite:

```
pip install flask
python setup_db.py --sqlite
```
macOS / Linux: `DB_ENGINE=sqlite python app.py` Windows: `$env:DB_ENGINE="sqlite"; python app.py`

The badge in the top-right corner shows which engine is running.

---

## Demo script (5 minutes, good for a viva)

1. **Dashboard** — point out the three lots, the colour-coded slots and the occupancy bars
   (`fn_occupancy_percent`).
2. **Vehicle entry** → plate `KA01AB1234`, lot *Central Mall* → the procedure allocates **A1**
   and the slot turns red on the dashboard (trigger).
3. On the ticket, press **Exit & generate bill** → hours and amount appear; the slot is
   green again. Nothing was calculated in Python — it is the trigger.
4. Choose **UPI** → **Record**. Try paying again: refused by the `UNIQUE` key.
5. **Vehicle entry** with a new plate, e.g. `KA09XY4321` → you get the registration form,
   then it is parked straight away.
6. **Bookings** → tick *Show every slot*, pick **C1** (maintenance) → the database refuses
   it with the trigger's message. Book a free slot instead → it turns amber (Reserved);
   **Check in** → red; exit → booking becomes *Completed*.
7. **Lots & rates** → set a rate to `0` → rejected by `chk_rate`.
8. **SQL reports** → all 17 queries, now reflecting what you just did.

## What was added beyond the report

The report's scripts (`01`–`03`) are used unchanged. `04_app_extensions.sql` adds what a
working app needs:

- **Booking lifecycle**: a confirmed booking marks its slot *Reserved*; cancelling frees it;
  `sp_booking_checkin` parks the vehicle in the booked slot; finishing the session marks the
  booking *Completed*.
- **Stricter booking check**: besides *Maintenance*, a booking is refused for a slot that is
  already taken or of the wrong vehicle type.
- **Safer procedures**: `sp_vehicle_entry` refuses a vehicle that is already parked and returns
  the new session id; `sp_vehicle_exit` refuses an already-closed session.
- **Minimum charge of 1 hour** in the billing trigger, so an immediate exit is not billed ₹0
  (`total_hours` still stores the real duration; the report's 7.12 h → ₹284.80 example is unchanged).

## Notes on the sample data

The report's sample data is loaded as-is, so a few things look odd until you act on them:

- Slots **A2**, **B2** (Central Mall) are marked *Occupied* and **T5** (Tech Park) *Reserved*
  without a matching session or booking. Use **Set available** on the lot page to clear them.
- Sessions 4 and 5 (Arjun Mehta, Priya Nair) have been "parked" since August 2026, so their
  running bill is large. Exit them to see the trigger bill weeks of parking.

## Project layout

```
app.py            Flask routes (all pages)
db.py             MySQL / SQLite connection, procedure calls, error messages
reports.py        the 17 report queries
setup_db.py       builds the database (handles DELIMITER blocks)
test_app.py       end-to-end tests of every workflow (python test_app.py)
sql/mysql/        01_schema, 02_sample_data, 03_views_triggers_procedures (from the report), 04_app_extensions
sql/sqlite/       schema.sql — the zero-setup demo copy
templates/        HTML pages
static/style.css  styling
```

## Troubleshooting

- **"Could not connect to MySQL"** — MySQL is not running, or `MYSQL_PASSWORD` is not set in the
  same terminal where you run `python app.py`.
- **`cryptography` package is required** — run `pip install cryptography` (MySQL 8's default login
  method needs it).
- **Error 1419 / "You do not have the SUPER privilege" while creating triggers** — run
  `SET GLOBAL log_bin_trust_function_creators = 1;` as root, then `python setup_db.py` again.
- **Port 5000 busy (macOS AirPlay)** — `PORT=5050 python app.py`.
