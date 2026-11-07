# Smart Parking Management System — working model

A web application on a **hybrid database**:

- **MySQL** holds every record that must be exact and linked: customers, vehicles, slots,
  bookings, sessions, bills, payments, staff logins. The design is normalised so each fact is
  stored once; anything that can be calculated (slot status, hours, session status) is
  calculated, and triggers and constraints refuse every insert, update and delete anomaly.
- **MongoDB** holds data whose shape varies from lot to lot: lot profiles with nested opening
  hours, amenities and EV chargers, and free-text customer reviews.

The two are joined in the application by `lot_id` and `session_id`.

| Screen | What it does | Database objects used |
| --- | --- | --- |
| Dashboard | Live slot map of every lot, occupancy bars, who is parked now, revenue | `vw_slot_status`, `vw_active_sessions`, `vw_slot_availability`, `fn_occupancy_percent()` |
| Vehicle entry | Type a plate, pick a lot → first free slot of the right type is allocated | `sp_vehicle_entry`, `trg_before_session_insert` |
| Sessions & billing | Exit a vehicle → bill computed → collect payment → leave a review | `sp_vehicle_exit`, `trg_before_session_update`, `trg_before_payment_insert`, Mongo `reviews` |
| Bookings | Reserve a slot, check in against the booking, or cancel | `trg_before_booking_insert`, `trg_before_booking_update`, `sp_booking_checkin` |
| Customers | Register customers and vehicles (passwords stored hashed), parking history | `customer`, `vehicle` |
| Lots & rates | Slot map, maintenance, rate card, staff, lot profile, chargers, reviews | `parking_slot`, `parking_rate`, `staff`, `vw_revenue_per_lot`, Mongo `lot_profiles` |
| SQL reports | The 17 SQL test queries, run live | joins, subqueries, GROUP BY/HAVING, window function, views |
| MongoDB | Collections, nested documents, 4 nested queries, SQL + Mongo combined | `lot_profiles`, `reviews`, `$elemMatch`, dot notation, aggregation |

## Employee login

Every page requires a staff sign-in. Accounts live in the `staff_account` table (one per row of
`staff`, password stored as a salted PBKDF2 hash). The role comes from `staff.designation`:

| Username | Role | Lot |
|---|---|---|
| `suresh.kumar` | Manager | Central Mall |
| `ravi.teja` | Manager | Tech Park |
| `manoj.pillai` | Attendant | Central Mall |
| `lakshmi.devi` | Attendant | Railway Station |
| `ganesh.naik` | Security | Tech Park |

Demo password for all of them: **`staff@123`**.

- **Attendants and security** can run entry, exit, billing, payments, bookings, customers and reports.
- **Managers** can also add slots, switch maintenance on and off, edit the rate card, and add staff
  (giving each new employee a username and password) or deactivate a staff login.
- Sessions last one shift (9 hours); **Sign out** is in the top-right corner.

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
   and the slot turns red on the dashboard (its status is calculated from the new session).
3. On the ticket, press **Exit & generate bill** → hours and amount appear; the slot is
   green again. The bill comes from a trigger, not from Python.
4. Choose **UPI** → **Record**. Try paying again: refused by the `UNIQUE` key.
5. **Vehicle entry** with a new plate, e.g. `KA09XY4321` → you get the registration form,
   then it is parked straight away.
6. **Bookings** → tick *Show every slot*, pick **C1** (maintenance) → the database refuses
   it with the trigger's message. Book a free slot instead → it turns amber (Reserved);
   **Check in** → red; exit → booking becomes *Completed*.
7. **Lots & rates** → set a rate to `0` → rejected by `chk_rate`.
8. **SQL reports** → all 17 queries, now reflecting what you just did.
9. Back on the paid ticket, **Save review** → stored in MongoDB. Open **MongoDB** → the combined
   SQL + MongoDB table and the nested queries.

## MongoDB setup

The app reads the connection from `MONGO_URI`:

| `MONGO_URI` | What happens |
|---|---|
| not set (default) | In-memory MongoDB (mongomock), filled with sample documents. Zero setup; used by the live demo. |
| `mongodb://localhost:27017` | Real MongoDB on your laptop (install *MongoDB Community Server*; it runs as a Windows service). |
| `mongodb+srv://...` | MongoDB Atlas (free cloud cluster). |

On first connection the app creates the two collections, inserts the sample documents and the
unique indexes (`lot_profiles.lot_id`, `reviews.session_id`). If MongoDB can't be reached, the
MongoDB panels say "unavailable" and everything stored in SQL keeps working.

## Design rules (no redundancy, no anomalies)

- Slot status is **calculated** by `vw_slot_status` (maintenance flag + active session + confirmed booking).
- `session_status` and `total_hours` are **generated columns** computed from entry and exit time.
- Removed duplicated columns: `parking_lot.total_slots`, `booking.customer_id`, `booking.booking_date`,
  `payment.amount_paid`.
- Unique keys on generated columns: one car per slot, one slot per car, one confirmed booking per slot.
- Triggers refuse wrong-type or maintenance slots, a pre-booked car using a different slot, paying an
  unfinished stay, reopening a closed booking, and editing a finished bill.
- History is protected: sessions, payments, vehicles and customers with history cannot be deleted
  (`ON DELETE RESTRICT`).

## Project layout

```
app.py            Flask routes (all pages)
db.py             MySQL / SQLite connection, procedure calls, error messages
reports.py        the 17 report queries
setup_db.py       builds the database (handles DELIMITER blocks)
test_app.py       end-to-end tests of every workflow (python test_app.py)
sql/mysql/        01_schema, 02_sample_data, 03_views_triggers_procedures, 04_staff_accounts
mongo_store.py    MongoDB collections, sample documents and nested queries
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
