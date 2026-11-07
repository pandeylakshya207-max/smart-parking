"""End-to-end tests of the full parking workflow (runs on the SQLite demo DB).

    python test_app.py
"""
import os
import re
import tempfile
import unittest

_tmp = tempfile.mkdtemp()
os.environ["DB_ENGINE"] = "sqlite"
os.environ["SQLITE_PATH"] = os.path.join(_tmp, "test.db")

import db  # noqa: E402
import mongo_store as mongo  # noqa: E402
from app import app  # noqa: E402


def backdate(session_id, minutes):
    """Test-only: pretend a car arrived `minutes` ago. Entry times are locked by a
    trigger, so the trigger is lifted for this one statement and put back."""
    conn = db.get_conn()
    sql = conn.execute("SELECT sql FROM sqlite_master WHERE name='trg_before_session_update'").fetchone()[0]
    conn.execute("DROP TRIGGER trg_before_session_update")
    conn.execute("UPDATE parking_session SET entry_time = datetime('now','localtime',?) WHERE session_id=?",
                 (f"-{minutes} minutes", session_id))
    conn.execute(sql)
    conn.commit()

class ParkingFlow(unittest.TestCase):
    def setUp(self):
        db.init_sqlite(force=True)
        app.config["TESTING"] = True
        self.c = app.test_client()
        self.login("suresh.kumar")          # Manager, Central Mall

    def login(self, username, password="staff@123"):
        return self.c.post("/login", data={"username": username, "password": password})

    def q(self, sql, params=()):
        with app.app_context():
            return db.query(sql, params)

    def slot(self, lot_id, number):
        # status is calculated by the view, never stored
        return self.q("SELECT * FROM vw_slot_status WHERE lot_id=%s AND slot_number=%s", (lot_id, number))[0]

    # ------------------------------------------------------------------
    def test_every_page_renders(self):
        for url in ["/", "/entry", "/sessions", "/sessions?status=unpaid", "/sessions/1", "/bookings",
                    "/customers", "/customers?q=KA01", "/customers/1", "/customers/new", "/lots",
                    "/lots/1", "/lots/2", "/lots/3", "/reports", "/api/slots"]:
            r = self.c.get(url)
            self.assertEqual(r.status_code, 200, url)
        self.assertEqual(self.c.get("/sessions/999").status_code, 404)

    def test_reports_match_report_document(self):
        html = self.c.get("/reports").get_data(as_text=True)
        self.assertNotIn('class="flash error"', html)
        # Q11 window function and Q4 revenue from the report's sample data
        self.assertIn("393.75", html)
        self.assertIn("Karan Verma", html)

    def test_walk_in_entry_exit_bill_and_pay(self):
        # Vikram Rao (vehicle 3, Car) enters Central Mall: first free Car slot is A1
        r = self.c.post("/entry", data={"vehicle_number": "ka 03 ef 9012", "lot_id": 1})
        self.assertEqual(r.status_code, 302)
        sid = int(re.search(r"/sessions/(\d+)", r.location).group(1))
        self.assertEqual(self.slot(1, "A1")["status"], "Occupied")        # calculated by vw_slot_status

        # entering twice is refused
        r = self.c.post("/entry", data={"vehicle_number": "KA03EF9012", "lot_id": 3}, follow_redirects=True)
        self.assertIn("already parked", r.get_data(as_text=True))

        # back-date entry to make a 2.5 h stay, then exit
        with app.app_context():
            backdate(sid, 150)
        r = self.c.post(f"/sessions/{sid}/exit")
        self.assertEqual(r.status_code, 302)
        s = self.q("SELECT * FROM parking_session WHERE session_id=%s", (sid,))[0]
        self.assertEqual(s["session_status"], "Completed")
        self.assertAlmostEqual(s["total_hours"], 2.5, places=1)
        self.assertAlmostEqual(s["amount_due"], round(s["total_hours"] * 40, 2), places=2)   # Car @ ₹40
        self.assertEqual(self.slot(1, "A1")["status"], "Available")       # slot freed

        # exiting again is refused
        r = self.c.post(f"/sessions/{sid}/exit", follow_redirects=True)
        self.assertIn("already completed", r.get_data(as_text=True))

        # pay, and double payment is refused by UNIQUE(session_id)
        self.c.post(f"/sessions/{sid}/pay", data={"payment_mode": "UPI"})
        p = self.q("SELECT * FROM payment WHERE session_id=%s", (sid,))
        self.assertEqual(len(p), 1)
        self.assertNotIn("amount_paid", p[0])                              # amount stored once, on the bill
        r = self.c.post(f"/sessions/{sid}/pay", data={"payment_mode": "Cash"}, follow_redirects=True)
        self.assertEqual(len(self.q("SELECT * FROM payment WHERE session_id=%s", (sid,))), 1)

    def test_unregistered_vehicle_registers_then_parks(self):
        r = self.c.post("/entry", data={"vehicle_number": "KA09ZZ0001", "lot_id": 2})
        self.assertIn("/customers/new", r.location)
        r = self.c.post("/customers/new", data={
            "lot_id": 2, "full_name": "Test Driver", "phone": "9000000001", "email": "t@x.com",
            "password": "secret", "vehicle_number": "KA09ZZ0001", "vehicle_type": "EV", "model_name": "MG ZS"})
        self.assertIn("/sessions/", r.location)
        self.assertEqual(self.slot(2, "T3")["status"], "Occupied")        # only EV slot at Tech Park
        cust = self.q("SELECT password_hash FROM customer WHERE email='t@x.com'")[0]
        self.assertNotEqual(cust["password_hash"], "secret")
        # duplicate email is rejected by UNIQUE
        r = self.c.post("/customers/new", data={
            "full_name": "Dup", "phone": "9000000002", "email": "t@x.com", "password": "x1234",
            "vehicle_number": "", "vehicle_type": "Car"})
        self.assertIn("already exists", r.get_data(as_text=True))

    def test_lot_full_for_type(self):
        # Railway Station has one Bike slot (R2) and it is occupied
        r = self.c.post("/entry", data={"vehicle_number": "KA02CD5678", "lot_id": 3}, follow_redirects=True)
        self.assertIn("No available slot for this vehicle type", r.get_data(as_text=True))

    def test_booking_reserve_checkin_exit_completes_booking(self):
        a3 = self.slot(1, "A3")
        r = self.c.post("/bookings", data={"vehicle_id": 3, "slot_id": a3["slot_id"],
                                           "start_time": "2026-11-01T10:00", "end_time": "2026-11-01T12:00"},
                        follow_redirects=True)
        self.assertIn("confirmed", r.get_data(as_text=True))
        self.assertEqual(self.slot(1, "A3")["status"], "Reserved")
        bid = self.q("SELECT MAX(booking_id) AS b FROM booking")[0]["b"]

        # walk-in allocation must skip the reserved slot
        self.c.post("/entry", data={"vehicle_number": "KA07MN6789", "lot_id": 1})
        self.assertEqual(self.slot(1, "A1")["status"], "Occupied")
        self.assertEqual(self.slot(1, "A3")["status"], "Reserved")

        r = self.c.post(f"/bookings/{bid}/checkin")
        sid = int(re.search(r"/sessions/(\d+)", r.location).group(1))
        self.assertEqual(self.slot(1, "A3")["status"], "Occupied")
        self.c.post(f"/sessions/{sid}/exit")
        self.assertEqual(self.q("SELECT booking_status FROM booking WHERE booking_id=%s", (bid,))[0]["booking_status"],
                         "Completed")
        self.assertEqual(self.slot(1, "A3")["status"], "Available")

    def test_booking_rules_enforced_by_database(self):
        c1 = self.slot(1, "C1")   # Maintenance
        r = self.c.post("/bookings", data={"vehicle_id": 1, "slot_id": c1["slot_id"],
                                           "start_time": "2026-11-01T10:00", "end_time": "2026-11-01T12:00"},
                        follow_redirects=True)
        self.assertIn("under maintenance", r.get_data(as_text=True))
        b1 = self.slot(1, "B1")   # Bike slot, Car vehicle
        r = self.c.post("/bookings", data={"vehicle_id": 1, "slot_id": b1["slot_id"],
                                           "start_time": "2026-11-01T10:00", "end_time": "2026-11-01T12:00"},
                        follow_redirects=True)
        self.assertIn("does not match", r.get_data(as_text=True))
        a1 = self.slot(1, "A1")
        r = self.c.post("/bookings", data={"vehicle_id": 1, "slot_id": a1["slot_id"],
                                           "start_time": "2026-11-01T12:00", "end_time": "2026-11-01T10:00"},
                        follow_redirects=True)
        self.assertIn("End time must be after start time", r.get_data(as_text=True))
        self.assertEqual(self.slot(1, "A1")["status"], "Available")

    def test_cancel_booking_releases_slot(self):
        a1 = self.slot(1, "A1")
        self.c.post("/bookings", data={"vehicle_id": 1, "slot_id": a1["slot_id"],
                                       "start_time": "2026-11-01T10:00", "end_time": "2026-11-01T12:00"})
        bid = self.q("SELECT MAX(booking_id) AS b FROM booking")[0]["b"]
        self.assertEqual(self.slot(1, "A1")["status"], "Reserved")
        self.c.post(f"/bookings/{bid}/cancel")
        self.assertEqual(self.slot(1, "A1")["status"], "Available")

    def test_slot_maintenance_rate_and_staff(self):
        a1 = self.slot(1, "A1")
        self.c.post(f"/slots/{a1['slot_id']}/status", data={"action": "maintenance"})
        self.assertEqual(self.slot(1, "A1")["status"], "Maintenance")
        self.c.post(f"/slots/{a1['slot_id']}/status", data={"action": "available"})
        self.assertEqual(self.slot(1, "A1")["status"], "Available")
        # occupied slot with an active session cannot be released manually
        t1 = self.slot(2, "T1")
        r = self.c.post(f"/slots/{t1['slot_id']}/status", data={"action": "available"}, follow_redirects=True)
        self.assertEqual(self.slot(2, "T1")["status"], "Occupied")
        # rate CHECK > 0
        rid = self.q("SELECT rate_id FROM parking_rate WHERE lot_id=1 AND vehicle_type='Car'")[0]["rate_id"]
        r = self.c.post("/lots/1/rates", data={f"rate_{rid}": "0"}, follow_redirects=True)
        self.assertIn("rejected", r.get_data(as_text=True))
        self.c.post("/lots/1/rates", data={f"rate_{rid}": "50"})
        self.assertEqual(self.q("SELECT rate_per_hour FROM parking_rate WHERE rate_id=%s", (rid,))[0]["rate_per_hour"], 50)
        # new slot + duplicate slot number
        self.c.post("/lots/1/slots", data={"slot_number": "a9", "floor_number": 1, "slot_type": "Car"})
        self.assertEqual(self.slot(1, "A9")["status"], "Available")
        r = self.c.post("/lots/1/slots", data={"slot_number": "A9", "floor_number": 1, "slot_type": "Car"},
                        follow_redirects=True)
        self.assertIn("Slot not added", r.get_data(as_text=True))
        self.c.post("/lots/1/staff", data={"full_name": "New Guard", "designation": "Security",
                                          "shift": "Night", "phone": "9880099999",
                                          "username": "new.guard", "password": "guard@1"})
        self.assertEqual(len(self.q("SELECT * FROM staff WHERE lot_id=1")), 3)

    def test_minimum_one_hour_charge(self):
        r = self.c.post("/entry", data={"vehicle_number": "KA02CD5678", "lot_id": 1})
        sid = int(re.search(r"/sessions/(\d+)", r.location).group(1))
        self.c.post(f"/sessions/{sid}/exit")
        s = self.q("SELECT * FROM parking_session WHERE session_id=%s", (sid,))[0]
        self.assertLess(s["total_hours"], 0.1)
        self.assertEqual(s["amount_due"], 15.0)          # Bike @ ₹15, 1 h minimum


class StaffLogin(unittest.TestCase):
    def setUp(self):
        db.init_sqlite(force=True)
        app.config["TESTING"] = True
        self.c = app.test_client()

    def test_pages_require_login(self):
        for url in ["/", "/entry", "/sessions", "/bookings", "/customers", "/lots/1", "/reports"]:
            r = self.c.get(url)
            self.assertEqual(r.status_code, 302, url)
            self.assertIn("/login", r.location)
        self.assertEqual(self.c.get("/api/slots").status_code, 401)
        self.assertEqual(self.c.post("/entry", data={"vehicle_number": "KA03EF9012", "lot_id": 1}).status_code, 302)
        with app.app_context():
            self.assertEqual(db.query("SELECT COUNT(*) AS n FROM parking_session", one=True)["n"], 6)

    def test_login_page_and_bad_password(self):
        self.assertEqual(self.c.get("/login").status_code, 200)
        r = self.c.post("/login", data={"username": "suresh.kumar", "password": "wrong"})
        self.assertEqual(r.status_code, 401)
        self.assertIn("Incorrect username or password", r.get_data(as_text=True))
        r = self.c.post("/login", data={"username": "nobody", "password": "staff@123"})
        self.assertEqual(r.status_code, 401)

    def test_login_redirects_back_and_logout(self):
        r = self.c.get("/reports")
        nxt = r.location.split("next=")[1]
        from urllib.parse import unquote
        r = self.c.post("/login", data={"username": "  Manoj.Pillai ", "password": "staff@123", "next": unquote(nxt)})
        self.assertEqual(r.location, "/reports")
        html = self.c.get("/").get_data(as_text=True)
        self.assertIn("Manoj Pillai", html)
        with app.app_context():
            self.assertIsNotNone(db.query("SELECT last_login FROM staff_account WHERE staff_id=2", one=True)["last_login"])
        self.c.post("/logout")
        self.assertEqual(self.c.get("/").status_code, 302)

    def test_open_redirect_blocked(self):
        r = self.c.post("/login", data={"username": "suresh.kumar", "password": "staff@123", "next": "//evil.example"})
        self.assertEqual(r.location, "/")
        r = self.c.post("/login", data={"username": "suresh.kumar", "password": "staff@123", "next": "https://evil.example"})
        self.assertEqual(r.location, "/")

    def test_attendant_cannot_change_rates_slots_or_staff(self):
        self.c.post("/login", data={"username": "manoj.pillai", "password": "staff@123"})
        with app.app_context():
            rid = db.query("SELECT rate_id FROM parking_rate WHERE lot_id=1 AND vehicle_type='Car'", one=True)["rate_id"]
            a1 = db.query("SELECT slot_id FROM parking_slot WHERE slot_number='A1'", one=True)["slot_id"]
        r = self.c.post("/lots/1/rates", data={f"rate_{rid}": "99"}, follow_redirects=True)
        self.assertIn("Only a Manager", r.get_data(as_text=True))
        self.c.post(f"/slots/{a1}/status", data={"action": "maintenance"})
        self.c.post("/lots/1/slots", data={"slot_number": "Z9", "floor_number": 1, "slot_type": "Car"})
        self.c.post("/lots/1/staff", data={"full_name": "X", "designation": "Manager", "shift": "Night",
                                          "phone": "1", "username": "xx.yy", "password": "secret1"})
        with app.app_context():
            self.assertEqual(db.query("SELECT rate_per_hour FROM parking_rate WHERE rate_id=%s", (rid,), one=True)["rate_per_hour"], 40)
            self.assertEqual(db.query("SELECT status FROM vw_slot_status WHERE slot_id=%s", (a1,), one=True)["status"], "Available")
            self.assertIsNone(db.query("SELECT 1 FROM parking_slot WHERE slot_number='Z9'", one=True))
            self.assertIsNone(db.query("SELECT 1 FROM staff_account WHERE username='xx.yy'", one=True))
        # but attendants can still run entry and exit
        r = self.c.post("/entry", data={"vehicle_number": "KA03EF9012", "lot_id": 1})
        self.assertIn("/sessions/", r.location)
        html = self.c.get("/lots/1").get_data(as_text=True)
        self.assertNotIn("Add staff", html)
        self.assertIn("Only a Manager can change rates", html)

    def test_manager_creates_staff_login(self):
        self.c.post("/login", data={"username": "ravi.teja", "password": "staff@123"})
        r = self.c.post("/lots/2/staff", data={"full_name": "Kavya Rao", "designation": "Attendant", "shift": "Evening",
                                              "phone": "9880077777", "username": "kavya.rao", "password": "kavya@1"},
                        follow_redirects=True)
        self.assertIn("can now sign in as kavya.rao", r.get_data(as_text=True))
        # duplicate username refused, and no orphan staff row is created
        self.c.post("/lots/2/staff", data={"full_name": "Dup", "designation": "Attendant", "shift": "Evening",
                                          "phone": "1", "username": "kavya.rao", "password": "kavya@1"})
        with app.app_context():
            self.assertEqual(db.query("SELECT COUNT(*) AS n FROM staff WHERE full_name='Dup'", one=True)["n"], 0)
        self.c.post("/logout")
        r = self.c.post("/login", data={"username": "kavya.rao", "password": "kavya@1"})
        self.assertEqual(r.status_code, 302)
        self.assertIn("Kavya Rao", self.c.get("/").get_data(as_text=True))

    def test_deactivated_account_is_signed_out(self):
        self.c.post("/login", data={"username": "manoj.pillai", "password": "staff@123"})
        self.assertEqual(self.c.get("/").status_code, 200)
        with app.app_context():
            db.execute("UPDATE staff_account SET is_active = 0 WHERE staff_id = 2")
        self.assertEqual(self.c.get("/").status_code, 302)
        self.assertEqual(self.c.post("/login", data={"username": "manoj.pillai", "password": "staff@123"}).status_code, 401)


    def test_manager_disables_and_enables_staff_login(self):
        self.c.post("/login", data={"username": "suresh.kumar", "password": "staff@123"})
        self.assertIn("Disable login", self.c.get("/lots/1").get_data(as_text=True))
        r = self.c.post("/staff/2/login", follow_redirects=True)
        self.assertIn("can no longer sign in", r.get_data(as_text=True))
        r = self.c.post("/staff/1/login", follow_redirects=True)          # own account
        self.assertIn("cannot disable your own login", r.get_data(as_text=True))
        other = app.test_client()
        self.assertEqual(other.post("/login", data={"username": "manoj.pillai", "password": "staff@123"}).status_code, 401)
        self.c.post("/staff/2/login")
        self.assertEqual(other.post("/login", data={"username": "manoj.pillai", "password": "staff@123"}).status_code, 302)
        # an attendant cannot toggle anyone
        other.post("/staff/1/login")
        with app.app_context():
            self.assertEqual(db.query("SELECT is_active FROM staff_account WHERE staff_id=1", one=True)["is_active"], 1)

class AnomalyRules(unittest.TestCase):
    """Every anomaly found in the design audit must now be refused by the database."""

    def setUp(self):
        db.init_sqlite(force=True)
        self.ctx = app.app_context()
        self.ctx.push()

    def tearDown(self):
        db.close_conn()
        self.ctx.pop()

    def refused(self, sql, params=(), text=None):
        with self.assertRaises(db.DBError) as cm:
            db.execute(sql, params)
        if text:
            self.assertIn(text, str(cm.exception))

    def test_redundant_columns_are_gone(self):
        cols = lambda t: {r["name"] for r in db.query(f"PRAGMA table_xinfo({t})")}
        self.assertNotIn("status", cols("parking_slot"))
        self.assertNotIn("total_slots", cols("parking_lot"))
        self.assertNotIn("customer_id", cols("booking"))
        self.assertNotIn("booking_date", cols("booking"))
        self.assertNotIn("amount_paid", cols("payment"))

    def test_sample_data_has_no_phantom_status(self):
        busy = {r["slot_number"]: r["status"] for r in
                db.query("SELECT slot_number, status FROM vw_slot_status WHERE status <> 'Available'")}
        self.assertEqual(busy, {"B3": "Reserved", "C1": "Maintenance", "T1": "Occupied", "R2": "Occupied"})

    def test_generated_columns_follow_exit_time(self):
        s = db.query("SELECT session_status, total_hours FROM parking_session WHERE session_id=1", one=True)
        self.assertEqual((s["session_status"], s["total_hours"]), ("Completed", 4.08))
        self.refused("UPDATE parking_session SET session_status='Completed' WHERE session_id=4")

    def test_insertion_anomalies_refused(self):
        now = "2026-11-07 10:00:00"
        ins = "INSERT INTO parking_session (booking_id, vehicle_id, slot_id, entry_time) VALUES (%s, %s, %s, %s)"
        self.refused(ins, (None, 1, 9, now), "already occupied")          # T1 has a car
        self.refused(ins, (None, 5, 10, now), "already parked")           # vehicle 5 is parked
        self.refused(ins, (None, 1, 8, now), "maintenance")               # C1
        self.refused(ins, (None, 2, 1, now), "does not match")            # bike in car slot
        self.refused(ins, (None, 4, 7, now), "reserved for another")      # B3 booked
        self.refused(ins, (2, 1, 7, now), "booked vehicle and slot")      # wrong car for booking 2
        self.refused("INSERT INTO booking (vehicle_id, slot_id, start_time, end_time) VALUES (4, 7, %s, %s)",
                     ("2026-12-01 10:00:00", "2026-12-01 11:00:00"), "occupied or reserved")
        self.refused("INSERT INTO payment (session_id, payment_mode) VALUES (4, 'UPI')", (), "completed session")

    def test_update_anomalies_refused(self):
        self.refused("UPDATE parking_session SET amount_due = 1 WHERE session_id = 1", (), "cannot be changed")
        self.refused("UPDATE parking_session SET exit_time = '2026-08-20 15:00:00' WHERE session_id = 1", (),
                     "cannot be changed")
        self.refused("UPDATE booking SET booking_status = 'Confirmed' WHERE booking_id = 4", (), "reopened")

    def test_deletion_anomalies_refused(self):
        self.refused("DELETE FROM customer WHERE customer_id = 1", (), "history is protected")
        self.refused("DELETE FROM parking_session WHERE session_id = 1", (), "history is protected")
        self.refused("DELETE FROM vehicle WHERE vehicle_id = 1", (), "history is protected")
        self.assertEqual(db.query("SELECT COUNT(*) AS n FROM payment", one=True)["n"], 4)

class MongoHybrid(unittest.TestCase):
    """MongoDB collections, nested queries, the SQL+Mongo workflow, and failure handling."""

    def setUp(self):
        db.init_sqlite(force=True)
        mongo.reset("memory")
        app.config["TESTING"] = True
        self.c = app.test_client()
        self.c.post("/login", data={"username": "suresh.kumar", "password": "staff@123"})

    def tearDown(self):
        mongo.reset("memory")

    def test_nested_queries(self):
        res = {q["code"]: mongo.run_nested(q) for q in mongo.NESTED_QUERIES}
        self.assertEqual([r["lot_id"] for r in res["M1"]], [1])          # only Central Mall has 60 kW CCS2
        self.assertEqual([r["lot_id"] for r in res["M2"]], [2])          # Tech Park is 24 h
        self.assertEqual(sorted(r["session_id"] for r in res["M3"]), [2, 6])
        m4 = {r["_id"]: r for r in res["M4"]}
        self.assertEqual(m4[1]["reviews"], 2)
        self.assertAlmostEqual(m4[1]["avg_rating"], 4.5)

    def test_mongodb_page_combines_sql_and_mongo(self):
        html = self.c.get("/mongodb").get_data(as_text=True)
        self.assertIn("Combined result", html)
        self.assertIn("4.5 ★", html)                       # Mongo rating for Central Mall
        self.assertIn("₹189.45", html)                     # SQL revenue for Central Mall
        self.assertIn("ev_chargers", html)

    def test_review_workflow_needs_paid_sql_session(self):
        # session 4 is still parked (unpaid): review refused by the SQL check
        r = self.c.post("/sessions/4/review", data={"rating": 5, "safety": 5, "cleanliness": 5,
                                                   "ease_of_parking": 5}, follow_redirects=True)
        self.assertIn("Only a paid visit", r.get_data(as_text=True))
        # park, exit, pay, then review
        r = self.c.post("/entry", data={"vehicle_number": "KA01AB1234", "lot_id": 1})
        sid = int(re.search(r"/sessions/(\d+)", r.location).group(1))
        self.c.post(f"/sessions/{sid}/exit")
        self.c.post(f"/sessions/{sid}/pay", data={"payment_mode": "UPI"})
        form = {"rating": 4, "safety": 5, "cleanliness": 4, "ease_of_parking": 3, "comment": "Good",
                "tags": ["safe", "clean"]}
        r = self.c.post(f"/sessions/{sid}/review", data=form, follow_redirects=True)
        self.assertIn("Review saved in MongoDB", r.get_data(as_text=True))
        doc = mongo.review_for_session(sid)
        self.assertEqual((doc["lot_id"], doc["aspects"]["safety"], doc["tags"]), (1, 5, ["safe", "clean"]))
        r = self.c.post(f"/sessions/{sid}/review", data=form, follow_redirects=True)
        self.assertIn("already has a review", r.get_data(as_text=True))   # unique index on session_id

    def test_add_charger_checks_sql_then_pushes_nested(self):
        r = self.c.post("/lots/1/chargers", data={"slot_number": "A1", "connector": "CCS2", "power_kw": 50},
                        follow_redirects=True)
        self.assertIn("existing EV slot", r.get_data(as_text=True))         # A1 is a Car slot in SQL
        self.c.post("/lots/1/chargers", data={"slot_number": "B3", "connector": "CHAdeMO", "power_kw": 50})
        chargers = mongo.lot_profile(1)["ev_chargers"]
        self.assertEqual(len(chargers), 3)
        self.assertEqual(chargers[-1]["connector"], "CHAdeMO")

    def test_app_keeps_working_when_mongodb_is_down(self):
        mongo.reset("mongodb://127.0.0.1:1/?serverSelectionTimeoutMS=300")
        for url in ["/", "/lots/1", "/mongodb", "/sessions/1", "/reports"]:
            self.assertEqual(self.c.get(url).status_code, 200, url)
        self.assertIn("MongoDB is unavailable", self.c.get("/lots/1").get_data(as_text=True))
        # SQL work still succeeds
        r = self.c.post("/entry", data={"vehicle_number": "KA01AB1234", "lot_id": 1})
        self.assertIn("/sessions/", r.location)

if __name__ == "__main__":
    unittest.main(verbosity=2)
