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
from app import app  # noqa: E402


class ParkingFlow(unittest.TestCase):
    def setUp(self):
        db.init_sqlite(force=True)
        app.config["TESTING"] = True
        self.c = app.test_client()

    def q(self, sql, params=()):
        with app.app_context():
            return db.query(sql, params)

    def slot(self, lot_id, number):
        return self.q("SELECT * FROM parking_slot WHERE lot_id=%s AND slot_number=%s", (lot_id, number))[0]

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
        self.assertEqual(self.slot(1, "A1")["status"], "Occupied")        # trg_after_session_insert

        # entering twice is refused
        r = self.c.post("/entry", data={"vehicle_number": "KA03EF9012", "lot_id": 3}, follow_redirects=True)
        self.assertIn("already parked", r.get_data(as_text=True))

        # back-date entry to make a 2.5 h stay, then exit
        with app.app_context():
            db.execute("UPDATE parking_session SET entry_time = datetime('now','localtime','-150 minutes') "
                       "WHERE session_id=%s", (sid,))
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
        self.assertEqual(p[0]["amount_paid"], s["amount_due"])
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
                                          "shift": "Night", "phone": "9880099999"})
        self.assertEqual(len(self.q("SELECT * FROM staff WHERE lot_id=1")), 3)

    def test_minimum_one_hour_charge(self):
        r = self.c.post("/entry", data={"vehicle_number": "KA02CD5678", "lot_id": 1})
        sid = int(re.search(r"/sessions/(\d+)", r.location).group(1))
        self.c.post(f"/sessions/{sid}/exit")
        s = self.q("SELECT * FROM parking_session WHERE session_id=%s", (sid,))[0]
        self.assertLess(s["total_hours"], 0.1)
        self.assertEqual(s["amount_due"], 15.0)          # Bike @ ₹15, 1 h minimum


if __name__ == "__main__":
    unittest.main(verbosity=2)
