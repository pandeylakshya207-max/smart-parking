"""Smart Parking Management System — web application (Flask).

Run:
    python app.py                      # MySQL (see README for settings)
    DB_ENGINE=sqlite python app.py     # zero-setup demo database
Then open http://127.0.0.1:5000
"""
import json
import os
import re
from datetime import datetime, timedelta
from functools import wraps

from flask import (Flask, abort, flash, g, jsonify, redirect, render_template,
                   request, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

import db
import mongo_store as mongo
from db import DBError
from mongo_store import MongoUnavailable
from reports import REPORT_QUERIES

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "spms-dev-key")
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",                 # blocks cross-site form posts (CSRF)
    PERMANENT_SESSION_LIFETIME=timedelta(hours=9),  # one shift
)
app.teardown_appcontext(db.close_conn)

STAFF_HASH = "pbkdf2:sha256:100000"   # fast enough for a 0.1-CPU host, still salted + iterated
PUBLIC_ENDPOINTS = {"login", "static"}

VEHICLE_TYPES = ["Car", "Bike", "EV", "Handicap"]
PAYMENT_MODES = ["UPI", "Cash", "Card", "Wallet"]
REVIEW_TAGS = ["safe", "clean", "well-lit", "helpful staff", "quick exit", "crowded", "hard to find"]
CONNECTORS = ["CCS2", "Type 2", "CHAdeMO", "Bharat AC-001"]
SHIFTS = ["Morning", "Evening", "Night"]


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def norm_plate(s):
    return re.sub(r"[^A-Z0-9]", "", (s or "").upper())


def parse_dt(s):
    return datetime.strptime(s[:19].replace("T", " "), "%Y-%m-%d %H:%M:%S" if len(s) > 16 else "%Y-%m-%d %H:%M")


def elapsed_hours(entry_time):
    return max((datetime.now() - parse_dt(str(entry_time))).total_seconds() / 3600.0, 0)


@app.template_filter("dur")
def fmt_duration(hours):
    if hours is None:
        return "—"
    mins = int(round(float(hours) * 60))
    h, m = divmod(mins, 60)
    return f"{h}h {m:02d}m" if h else f"{m}m"


@app.template_filter("inr")
def fmt_inr(v):
    return "—" if v is None else "₹{:,.2f}".format(float(v))


@app.template_filter("dt")
def fmt_dt(v):
    if not v:
        return "—"
    try:
        return parse_dt(str(v)).strftime("%d %b %Y, %I:%M %p")
    except ValueError:
        return str(v)


@app.context_processor
def inject_globals():
    return {"engine": db.engine_label(), "mongo_label": mongo.status_label(),
            "now": datetime.now(), "user": g.get("user")}


# --------------------------------------------------------------------------
# staff authentication
# --------------------------------------------------------------------------
def load_staff(staff_id):
    return db.query("""SELECT st.staff_id, st.full_name, st.designation, st.shift, st.lot_id,
                              pl.lot_name, sa.username, sa.is_active
                       FROM staff_account sa
                       JOIN staff st       ON st.staff_id = sa.staff_id
                       JOIN parking_lot pl ON pl.lot_id   = st.lot_id
                       WHERE sa.staff_id = %s""", (staff_id,), one=True)


def safe_next(target):
    """Only allow redirects back into this site."""
    if target and target.startswith("/") and not target.startswith("//") and "\\" not in target:
        return target
    return url_for("dashboard")


@app.before_request
def require_login():
    g.user = None
    if request.endpoint in PUBLIC_ENDPOINTS or request.endpoint is None:
        return None
    sid = session.get("staff_id")
    if sid:
        u = load_staff(sid)
        if u and u["is_active"]:
            u["is_manager"] = u["designation"].strip().lower() == "manager"
            g.user = u
            return None
        session.clear()
    if request.path.startswith("/api/"):
        return jsonify({"error": "login required"}), 401
    return redirect(url_for("login", next=request.full_path.rstrip("?")))


def manager_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not g.user or not g.user["is_manager"]:
            flash("Only a Manager can change slots, rates or staff.", "error")
            return redirect(request.referrer or url_for("dashboard"))
        return view(*args, **kwargs)
    return wrapped


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("staff_id") and request.method == "GET":
        return redirect(url_for("dashboard"))
    error = None
    username = ""
    if request.method == "POST":
        username = (request.form.get("username") or "").strip().lower()
        password = request.form.get("password") or ""
        acct = db.query("SELECT staff_id, password_hash, is_active FROM staff_account WHERE username = %s",
                        (username,), one=True)
        if acct and acct["is_active"] and check_password_hash(acct["password_hash"], password):
            session.clear()
            session.permanent = True
            session["staff_id"] = acct["staff_id"]
            db.execute("UPDATE staff_account SET last_login = NOW() WHERE staff_id = %s", (acct["staff_id"],))
            u = load_staff(acct["staff_id"])
            flash(f"Welcome, {u['full_name']} ({u['designation']}, {u['lot_name']}).", "success")
            return redirect(safe_next(request.form.get("next")))
        error = "Incorrect username or password."
    return render_template("login.html", error=error, username=username,
                           next=request.values.get("next", "")), (401 if error else 200)


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("You have been signed out.", "info")
    return redirect(url_for("login"))


def rate_for(slot_id, vehicle_id):
    r = db.query("""SELECT pr.rate_per_hour FROM parking_rate pr
                    JOIN parking_slot sl ON sl.lot_id = pr.lot_id
                    JOIN vehicle v ON v.vehicle_type = pr.vehicle_type
                    WHERE sl.slot_id = %s AND v.vehicle_id = %s""", (slot_id, vehicle_id), one=True)
    return r["rate_per_hour"] if r else None


def slot_label(slot_id):
    r = db.query("""SELECT sl.slot_number, sl.floor_number, pl.lot_name FROM parking_slot sl
                    JOIN parking_lot pl ON pl.lot_id = sl.lot_id WHERE sl.slot_id = %s""",
                 (slot_id,), one=True)
    return f"{r['slot_number']} (floor {r['floor_number']}, {r['lot_name']})" if r else str(slot_id)


def lots_with_slots():
    lots = db.query("""SELECT pl.lot_id, pl.lot_name, pl.location, pl.total_floors, pl.contact_number,
                              (SELECT COUNT(*) FROM parking_slot sl WHERE sl.lot_id = pl.lot_id) AS total_slots,
                              fn_occupancy_percent(pl.lot_id) AS occupancy
                       FROM parking_lot pl ORDER BY pl.lot_id""")
    # status is calculated by the view vw_slot_status — never stored
    slots = db.query("""SELECT ss.slot_id, ss.lot_id, ss.slot_number, ss.floor_number, ss.slot_type, ss.status,
                               v.vehicle_number, ss.active_session_id AS session_id
                        FROM vw_slot_status ss
                        LEFT JOIN vehicle v ON v.vehicle_id = ss.parked_vehicle_id
                        ORDER BY ss.lot_id, ss.floor_number, ss.slot_number""")
    for lot in lots:
        lot_slots = [s for s in slots if s["lot_id"] == lot["lot_id"]]
        lot["slots"] = lot_slots
        lot["counts"] = {st: sum(1 for s in lot_slots if s["status"] == st)
                         for st in ("Available", "Occupied", "Reserved", "Maintenance")}
        floors = sorted({s["floor_number"] for s in lot_slots})
        lot["floors"] = [(f, [s for s in lot_slots if s["floor_number"] == f]) for f in floors]
    return lots


# --------------------------------------------------------------------------
# dashboard
# --------------------------------------------------------------------------
@app.route("/")
def dashboard():
    lots = lots_with_slots()
    active = db.query("SELECT * FROM vw_active_sessions ORDER BY entry_time DESC")
    for a in active:
        a["hours"] = elapsed_hours(a["entry_time"])
    # the amount is stored once, on the bill (parking_session.amount_due)
    revenue = db.query("SELECT COALESCE(SUM(s.amount_due),0) AS total, COUNT(*) AS n FROM payment p "
                       "JOIN parking_session s ON s.session_id = p.session_id "
                       "WHERE p.payment_status = 'Paid'", one=True)
    today = db.query("SELECT COALESCE(SUM(s.amount_due),0) AS total FROM payment p "
                     "JOIN parking_session s ON s.session_id = p.session_id "
                     "WHERE DATE(p.payment_date) = DATE(NOW()) AND p.payment_status = 'Paid'", one=True)
    unpaid = db.query("""SELECT COUNT(*) AS n FROM parking_session s
                         LEFT JOIN payment p ON p.session_id = s.session_id
                         WHERE s.session_status = 'Completed' AND p.payment_id IS NULL""", one=True)
    availability = db.query("SELECT * FROM vw_slot_availability ORDER BY lot_id, slot_type")
    stats = {
        "slots": sum(len(l["slots"]) for l in lots),
        "free": sum(l["counts"]["Available"] for l in lots),
        "parked": len(active),
        "revenue": revenue["total"], "payments": revenue["n"],
        "today": today["total"], "unpaid": unpaid["n"],
    }
    return render_template("dashboard.html", lots=lots, active=active, stats=stats,
                           availability=availability)


@app.route("/api/slots")
def api_slots():
    lots = lots_with_slots()
    return jsonify({
        "slots": {s["slot_id"]: {"status": s["status"], "vehicle": s["vehicle_number"]}
                  for l in lots for s in l["slots"]},
        "lots": {l["lot_id"]: {"occupancy": l["occupancy"], "counts": l["counts"]} for l in lots},
    })


# --------------------------------------------------------------------------
# entry / exit / billing
# --------------------------------------------------------------------------
@app.route("/entry", methods=["GET", "POST"])
def entry():
    lots = db.query("SELECT lot_id, lot_name FROM parking_lot ORDER BY lot_id")
    if request.method == "POST":
        plate = norm_plate(request.form.get("vehicle_number"))
        lot_id = request.form.get("lot_id", type=int)
        if not plate or not lot_id:
            flash("Enter a vehicle number and choose a lot.", "error")
            return redirect(url_for("entry"))
        v = db.query("SELECT vehicle_id FROM vehicle WHERE vehicle_number = %s", (plate,), one=True)
        if not v:
            flash(f"{plate} is not registered yet. Register the owner and vehicle, and it will be parked straight away.", "info")
            return redirect(url_for("new_customer", vehicle_number=plate, lot_id=lot_id))
        return _do_entry(v["vehicle_id"], lot_id)
    vehicles = db.query("""SELECT v.vehicle_number, v.vehicle_type, c.full_name FROM vehicle v
                           JOIN customer c ON c.customer_id = v.customer_id ORDER BY v.vehicle_number""")
    avail = db.query("SELECT * FROM vw_slot_availability ORDER BY lot_id, slot_type")
    return render_template("entry.html", lots=lots, vehicles=vehicles, availability=avail,
                           types=VEHICLE_TYPES, preselect=request.args.get("lot_id", type=int))


def _do_entry(vehicle_id, lot_id):
    try:
        res = db.vehicle_entry(vehicle_id, lot_id)
    except DBError as e:
        flash(f"Entry refused by the database: {e}", "error")
        return redirect(url_for("entry", lot_id=lot_id))
    flash(f"sp_vehicle_entry allocated slot {slot_label(res['slot_id'])}; "
          f"vw_slot_status now shows it as Occupied.", "success")
    return redirect(url_for("session_detail", session_id=res["session_id"]))


@app.route("/sessions")
def sessions():
    status = request.args.get("status", "all")
    where = ""
    if status == "active":
        where = "WHERE s.session_status = 'Active'"
    elif status == "unpaid":
        where = "WHERE s.session_status = 'Completed' AND p.payment_id IS NULL"
    elif status == "completed":
        where = "WHERE s.session_status = 'Completed'"
    rows = db.query(f"""SELECT s.*, v.vehicle_number, v.vehicle_type, c.full_name, sl.slot_number,
                               pl.lot_name, p.payment_id, p.payment_mode
                        FROM parking_session s
                        JOIN vehicle v       ON v.vehicle_id = s.vehicle_id
                        JOIN customer c      ON c.customer_id = v.customer_id
                        JOIN parking_slot sl ON sl.slot_id = s.slot_id
                        JOIN parking_lot pl  ON pl.lot_id = sl.lot_id
                        LEFT JOIN payment p  ON p.session_id = s.session_id
                        {where}
                        ORDER BY s.session_status = 'Active' DESC, s.entry_time DESC""")
    for r in rows:
        if r["session_status"] == "Active":
            r["hours"] = elapsed_hours(r["entry_time"])
    return render_template("sessions.html", rows=rows, status=status)


@app.route("/sessions/<int:session_id>")
def session_detail(session_id):
    s = db.query("""SELECT s.*, v.vehicle_number, v.vehicle_type, v.model_name, v.vehicle_id,
                           c.full_name, c.phone, c.customer_id,
                           sl.slot_number, sl.floor_number, sl.lot_id, pl.lot_name, pl.location, pl.contact_number
                    FROM parking_session s
                    JOIN vehicle v       ON v.vehicle_id = s.vehicle_id
                    JOIN customer c      ON c.customer_id = v.customer_id
                    JOIN parking_slot sl ON sl.slot_id = s.slot_id
                    JOIN parking_lot pl  ON pl.lot_id = sl.lot_id
                    WHERE s.session_id = %s""", (session_id,), one=True)
    if not s:
        abort(404)
    s["rate"] = rate_for(s["slot_id"], s["vehicle_id"])
    if s["session_status"] == "Active":
        s["hours"] = elapsed_hours(s["entry_time"])
        s["billed_hours"] = max(round(s["hours"], 2), 1.0)
        s["estimate"] = round(s["billed_hours"] * s["rate"], 2) if s["rate"] else None
    elif s["total_hours"] is not None:
        s["billed_hours"] = max(s["total_hours"], 1.0)
    payment = db.query("SELECT * FROM payment WHERE session_id = %s", (session_id,), one=True)
    review, mongo_error = None, None
    if payment:                       # reviews live in MongoDB, linked by session_id
        try:
            review = mongo.review_for_session(session_id)
        except MongoUnavailable as e:
            mongo_error = str(e)
    return render_template("session.html", s=s, payment=payment, modes=PAYMENT_MODES,
                           review=review, mongo_error=mongo_error, review_tags=REVIEW_TAGS)


@app.route("/sessions/<int:session_id>/review", methods=["POST"])
def session_review(session_id):
    """Integrated workflow: SQL proves the visit was paid, MongoDB stores the review."""
    s = db.query("""SELECT s.session_id, sl.lot_id, v.vehicle_number, p.payment_id
                    FROM parking_session s
                    JOIN parking_slot sl ON sl.slot_id = s.slot_id
                    JOIN vehicle v       ON v.vehicle_id = s.vehicle_id
                    LEFT JOIN payment p  ON p.session_id = s.session_id
                    WHERE s.session_id = %s""", (session_id,), one=True)
    if not s or not s["payment_id"]:
        flash("Only a paid visit can be reviewed.", "error")
        return redirect(url_for("session_detail", session_id=session_id))
    f = request.form
    try:
        rating = int(f.get("rating", 0))
        aspects = {k: int(f.get(k, 0)) for k in ("safety", "cleanliness", "ease_of_parking")}
    except ValueError:
        rating, aspects = 0, {}
    if not 1 <= rating <= 5 or not all(1 <= v <= 5 for v in aspects.values()) or len(aspects) != 3:
        flash("Give every score from 1 to 5.", "error")
        return redirect(url_for("session_detail", session_id=session_id))
    tags = [t for t in f.getlist("tags") if t in REVIEW_TAGS]
    try:
        mongo.add_review(session_id, s["lot_id"], s["vehicle_number"], rating,
                         (f.get("comment") or "").strip()[:300], tags, aspects)
        flash("Review saved in MongoDB (collection reviews, linked to this session by session_id).", "success")
    except MongoUnavailable as e:
        flash(f"MongoDB is unavailable, so the review was not saved. Parking and billing are unaffected. ({e})", "error")
    except Exception as e:                   # unique index on session_id
        if "duplicate" in type(e).__name__.lower() or "duplicate" in str(e).lower():
            flash("This visit already has a review (one review per visit).", "error")
        else:
            raise
    return redirect(url_for("session_detail", session_id=session_id))


@app.route("/sessions/<int:session_id>/exit", methods=["POST"])
def session_exit(session_id):
    try:
        db.vehicle_exit(session_id)
    except DBError as e:
        flash(f"Exit refused by the database: {e}", "error")
        return redirect(request.referrer or url_for("sessions"))
    s = db.query("SELECT amount_due, total_hours FROM parking_session WHERE session_id = %s",
                 (session_id,), one=True)
    flash(f"sp_vehicle_exit stamped the exit time; trg_before_session_update billed "
          f"{fmt_duration(s['total_hours'])} = {fmt_inr(s['amount_due'])}, and the slot "
          f"is free again.", "success")
    return redirect(url_for("session_detail", session_id=session_id))


@app.route("/sessions/<int:session_id>/pay", methods=["POST"])
def session_pay(session_id):
    s = db.query("SELECT amount_due, session_status FROM parking_session WHERE session_id = %s",
                 (session_id,), one=True)
    if not s or s["session_status"] != "Completed" or s["amount_due"] is None:
        flash("Only a completed, billed session can be paid.", "error")
        return redirect(url_for("session_detail", session_id=session_id))
    mode = request.form.get("payment_mode")
    if mode not in PAYMENT_MODES:
        flash("Choose a payment mode.", "error")
        return redirect(url_for("session_detail", session_id=session_id))
    try:
        # no amount column: the payment settles the session's amount_due
        db.execute("INSERT INTO payment (session_id, payment_mode, payment_date, payment_status) "
                   "VALUES (%s, %s, NOW(), 'Paid')", (session_id, mode))
        flash(f"Payment of {fmt_inr(s['amount_due'])} recorded via {mode}.", "success")
    except DBError as e:
        flash(f"Payment not recorded: {e}", "error")
    return redirect(url_for("session_detail", session_id=session_id))


# --------------------------------------------------------------------------
# bookings
# --------------------------------------------------------------------------
@app.route("/bookings", methods=["GET", "POST"])
def bookings():
    if request.method == "POST":
        vehicle_id = request.form.get("vehicle_id", type=int)
        slot_id = request.form.get("slot_id", type=int)
        start, end = request.form.get("start_time", ""), request.form.get("end_time", "")
        v = db.query("SELECT vehicle_id FROM vehicle WHERE vehicle_id = %s", (vehicle_id,), one=True)
        if not v or not slot_id or not start or not end:
            flash("Fill in vehicle, slot, start and end time.", "error")
            return redirect(url_for("bookings"))
        try:
            st, en = parse_dt(start), parse_dt(end)
            # the customer is the vehicle's owner, and the date is part of start_time
            bid = db.execute("""INSERT INTO booking (vehicle_id, slot_id, start_time, end_time, booking_status)
                                VALUES (%s, %s, %s, %s, 'Confirmed')""",
                             (vehicle_id, slot_id,
                              st.strftime("%Y-%m-%d %H:%M:%S"), en.strftime("%Y-%m-%d %H:%M:%S")))
            flash(f"Booking #{bid} confirmed for slot {slot_label(slot_id)}; "
                  f"vw_slot_status now shows the slot as Reserved.", "success")
        except ValueError:
            flash("Times must be valid dates.", "error")
        except DBError as e:
            msg = str(e)
            if "chk_booking_time" in msg or "end_time" in msg:
                msg = "End time must be after start time (chk_booking_time)."
            flash(f"Booking refused by the database: {msg}", "error")
        return redirect(url_for("bookings"))

    rows = db.query("""SELECT b.*, c.full_name, v.vehicle_number, v.vehicle_type, sl.slot_number, pl.lot_name,
                              s.session_id
                       FROM booking b
                       JOIN vehicle v       ON v.vehicle_id = b.vehicle_id
                       JOIN customer c      ON c.customer_id = v.customer_id
                       JOIN parking_slot sl ON sl.slot_id = b.slot_id
                       JOIN parking_lot pl  ON pl.lot_id = sl.lot_id
                       LEFT JOIN parking_session s ON s.booking_id = b.booking_id
                       ORDER BY b.booking_status = 'Confirmed' DESC, b.start_time DESC""")
    vehicles = db.query("""SELECT v.vehicle_id, v.vehicle_number, v.vehicle_type, c.full_name FROM vehicle v
                           JOIN customer c ON c.customer_id = v.customer_id ORDER BY c.full_name""")
    slots = db.query("""SELECT ss.slot_id, ss.slot_number, ss.slot_type, ss.floor_number, ss.status, ss.lot_id,
                               pl.lot_name FROM vw_slot_status ss JOIN parking_lot pl ON pl.lot_id = ss.lot_id
                        ORDER BY ss.lot_id, ss.slot_number""")
    lots = db.query("SELECT lot_id, lot_name FROM parking_lot ORDER BY lot_id")
    return render_template("bookings.html", rows=rows, vehicles=vehicles, slots=slots, lots=lots)


@app.route("/bookings/<int:booking_id>/cancel", methods=["POST"])
def booking_cancel(booking_id):
    b = db.query("SELECT booking_status FROM booking WHERE booking_id = %s", (booking_id,), one=True)
    if not b or b["booking_status"] != "Confirmed":
        flash("Only confirmed bookings can be cancelled.", "error")
    else:
        db.execute("UPDATE booking SET booking_status = 'Cancelled' WHERE booking_id = %s", (booking_id,))
        flash(f"Booking #{booking_id} cancelled; the slot is free again (status is calculated, not stored).", "success")
    return redirect(url_for("bookings"))


@app.route("/bookings/<int:booking_id>/checkin", methods=["POST"])
def booking_checkin(booking_id):
    try:
        res = db.booking_checkin(booking_id)
    except DBError as e:
        flash(f"Check-in refused by the database: {e}", "error")
        return redirect(url_for("bookings"))
    flash(f"sp_booking_checkin opened a session in booked slot {slot_label(res['slot_id'])}.", "success")
    return redirect(url_for("session_detail", session_id=res["session_id"]))


# --------------------------------------------------------------------------
# customers & vehicles
# --------------------------------------------------------------------------
@app.route("/customers")
def customers():
    q = (request.args.get("q") or "").strip()
    like = f"%{q}%"
    rows = db.query("""SELECT c.*, COUNT(DISTINCT v.vehicle_id) AS vehicles,
                              GROUP_CONCAT(DISTINCT v.vehicle_number) AS plates
                       FROM customer c LEFT JOIN vehicle v ON v.customer_id = c.customer_id
                       WHERE c.full_name LIKE %s OR c.phone LIKE %s OR c.email LIKE %s
                             OR v.vehicle_number LIKE %s
                       GROUP BY c.customer_id, c.full_name, c.email, c.phone, c.password_hash, c.registered_on
                       ORDER BY c.full_name""", (like, like, like, like))
    return render_template("customers.html", rows=rows, q=q)


@app.route("/customers/new", methods=["GET", "POST"])
def new_customer():
    lot_id = request.values.get("lot_id", type=int)
    if request.method == "POST":
        f = request.form
        plate = norm_plate(f.get("vehicle_number"))
        try:
            cid = db.execute("INSERT INTO customer (full_name, email, phone, password_hash, registered_on) "
                             "VALUES (%s, %s, %s, %s, DATE(NOW()))",
                             (f["full_name"].strip(), f["email"].strip().lower(), f["phone"].strip(),
                              generate_password_hash(f["password"])))
        except DBError as e:
            flash(f"Customer not saved: {e}", "error")
            return render_template("customer_new.html", form=f, types=VEHICLE_TYPES, lot_id=lot_id)
        vid = None
        if plate:
            try:
                vid = db.execute("INSERT INTO vehicle (customer_id, vehicle_number, vehicle_type, model_name) "
                                 "VALUES (%s, %s, %s, %s)",
                                 (cid, plate, f["vehicle_type"], f.get("model_name") or None))
            except DBError as e:
                flash(f"Customer saved, but vehicle not added: {e}", "error")
                return redirect(url_for("customer_detail", customer_id=cid))
        flash(f"Registered {f['full_name']}" + (f" with vehicle {plate}." if plate else "."), "success")
        if vid and lot_id:
            return _do_entry(vid, lot_id)
        return redirect(url_for("customer_detail", customer_id=cid))
    form = {"vehicle_number": request.args.get("vehicle_number", "")}
    return render_template("customer_new.html", form=form, types=VEHICLE_TYPES, lot_id=lot_id)


@app.route("/customers/<int:customer_id>")
def customer_detail(customer_id):
    c = db.query("SELECT * FROM customer WHERE customer_id = %s", (customer_id,), one=True)
    if not c:
        abort(404)
    vehicles = db.query("SELECT * FROM vehicle WHERE customer_id = %s ORDER BY vehicle_id", (customer_id,))
    history = db.query("""SELECT s.*, v.vehicle_number, sl.slot_number, pl.lot_name, p.payment_mode
                          FROM parking_session s
                          JOIN vehicle v ON v.vehicle_id = s.vehicle_id
                          JOIN parking_slot sl ON sl.slot_id = s.slot_id
                          JOIN parking_lot pl ON pl.lot_id = sl.lot_id
                          LEFT JOIN payment p ON p.session_id = s.session_id
                          WHERE v.customer_id = %s ORDER BY s.entry_time DESC""", (customer_id,))
    spent = sum(h["amount_due"] or 0 for h in history if h["payment_mode"])
    return render_template("customer.html", c=c, vehicles=vehicles, history=history,
                           spent=spent, types=VEHICLE_TYPES)


@app.route("/customers/<int:customer_id>/vehicles", methods=["POST"])
def add_vehicle(customer_id):
    plate = norm_plate(request.form.get("vehicle_number"))
    if not plate:
        flash("Enter a vehicle number.", "error")
    else:
        try:
            db.execute("INSERT INTO vehicle (customer_id, vehicle_number, vehicle_type, model_name) "
                       "VALUES (%s, %s, %s, %s)",
                       (customer_id, plate, request.form.get("vehicle_type"),
                        request.form.get("model_name") or None))
            flash(f"Vehicle {plate} added.", "success")
        except DBError as e:
            flash(f"Vehicle not added: {e}", "error")
    return redirect(url_for("customer_detail", customer_id=customer_id))


# --------------------------------------------------------------------------
# lots, slots, rates, staff
# --------------------------------------------------------------------------
@app.route("/lots")
def lots():
    return render_template("lots.html", lots=lots_with_slots())


@app.route("/lots/<int:lot_id>")
def lot_detail(lot_id):
    lot = next((l for l in lots_with_slots() if l["lot_id"] == lot_id), None)
    if not lot:
        abort(404)
    rates = db.query("SELECT * FROM parking_rate WHERE lot_id = %s ORDER BY rate_id", (lot_id,))
    staff = db.query("""SELECT st.*, sa.username, sa.last_login, sa.is_active FROM staff st
                        LEFT JOIN staff_account sa ON sa.staff_id = st.staff_id
                        WHERE st.lot_id = %s ORDER BY st.staff_id""", (lot_id,))
    revenue = db.query("SELECT * FROM vw_revenue_per_lot WHERE lot_id = %s", (lot_id,), one=True)
    # MongoDB part of the page, joined to the SQL part by lot_id
    profile = reviews = rating = mongo_error = None
    try:
        profile = mongo.lot_profile(lot_id)
        reviews = mongo.reviews_for_lot(lot_id)
        rating = mongo.rating_summary().get(lot_id)
    except MongoUnavailable as e:
        mongo_error = str(e)
    ev_slots = [s["slot_number"] for s in lot["slots"] if s["slot_type"] == "EV"]
    return render_template("lot.html", lot=lot, rates=rates, staff=staff, revenue=revenue,
                           types=VEHICLE_TYPES, shifts=SHIFTS, profile=profile, reviews=reviews,
                           rating=rating, mongo_error=mongo_error, ev_slots=ev_slots,
                           connectors=CONNECTORS)


@app.route("/lots/<int:lot_id>/chargers", methods=["POST"])
@manager_required
def add_charger(lot_id):
    """Nested update: $push a charger sub-document, after SQL confirms the slot is an EV slot."""
    f = request.form
    slot_no = (f.get("slot_number") or "").strip().upper()
    slot = db.query("SELECT slot_type FROM parking_slot WHERE lot_id = %s AND slot_number = %s",
                    (lot_id, slot_no), one=True)
    if not slot or slot["slot_type"] != "EV":
        flash("Chargers can only be added to an existing EV slot of this lot (checked in SQL).", "error")
        return redirect(url_for("lot_detail", lot_id=lot_id))
    try:
        power = int(f.get("power_kw", 0))
    except ValueError:
        power = 0
    if f.get("connector") not in CONNECTORS or not 3 <= power <= 350:
        flash("Choose a connector and a power between 3 and 350 kW.", "error")
        return redirect(url_for("lot_detail", lot_id=lot_id))
    try:
        profile = mongo.lot_profile(lot_id) or {}
        n = len(profile.get("ev_chargers", [])) + 1
        prefix = "".join(w[0] for w in profile.get("lot_name", "LOT").split()[:2]).upper()
        mongo.add_ev_charger(lot_id, {"charger_id": f"{prefix}-EV{n}", "slot_number": slot_no,
                                      "connector": f["connector"], "power_kw": power,
                                      "network": (f.get("network") or "").strip()[:30] or "Own"})
        flash(f"Charger added to slot {slot_no} ($push into the nested ev_chargers array).", "success")
    except MongoUnavailable as e:
        flash(f"MongoDB is unavailable; charger not added. ({e})", "error")
    return redirect(url_for("lot_detail", lot_id=lot_id))


@app.route("/lots/<int:lot_id>/slots", methods=["POST"])
@manager_required
def add_slot(lot_id):
    f = request.form
    try:
        db.execute("INSERT INTO parking_slot (lot_id, slot_number, floor_number, slot_type) "
                   "VALUES (%s, %s, %s, %s)",
                   (lot_id, f["slot_number"].strip().upper(), int(f.get("floor_number") or 1), f["slot_type"]))
        flash(f"Slot {f['slot_number'].upper()} added.", "success")
    except (DBError, ValueError) as e:
        flash(f"Slot not added: {e}", "error")
    return redirect(url_for("lot_detail", lot_id=lot_id))


@app.route("/slots/<int:slot_id>/status", methods=["POST"])
@manager_required
def slot_status(slot_id):
    action = request.form.get("action")
    sl = db.query("SELECT lot_id, status FROM vw_slot_status WHERE slot_id = %s", (slot_id,), one=True)
    if not sl:
        abort(404)
    # Only "under maintenance" is stored; Occupied/Reserved come from sessions and bookings.
    if action == "maintenance":
        if sl["status"] in ("Occupied", "Reserved"):
            flash("Slot has a parked vehicle or a confirmed booking; it cannot go into maintenance.", "error")
        else:
            db.execute("UPDATE parking_slot SET under_maintenance = 1 WHERE slot_id = %s", (slot_id,))
            flash("Slot marked Maintenance. Entries and bookings on it are now refused by the triggers.", "success")
    elif action == "available":
        db.execute("UPDATE parking_slot SET under_maintenance = 0 WHERE slot_id = %s", (slot_id,))
        flash("Maintenance finished; the slot is back in service.", "success")
    return redirect(request.referrer or url_for("lot_detail", lot_id=sl["lot_id"]))


@app.route("/lots/<int:lot_id>/rates", methods=["POST"])
@manager_required
def update_rates(lot_id):
    changed, errors = 0, []
    for key, val in request.form.items():
        if not key.startswith("rate_"):
            continue
        try:
            db.execute("UPDATE parking_rate SET rate_per_hour = %s WHERE rate_id = %s AND lot_id = %s",
                       (float(val), int(key[5:]), lot_id))
            changed += 1
        except (DBError, ValueError) as e:
            errors.append(str(e))
    if errors:
        flash("Some rates were rejected (chk_rate requires a value above 0): " + errors[0], "error")
    else:
        flash("Rate card saved.", "success")
    return redirect(url_for("lot_detail", lot_id=lot_id))


@app.route("/lots/<int:lot_id>/staff", methods=["POST"])
@manager_required
def add_staff(lot_id):
    f = request.form
    username = (f.get("username") or "").strip().lower()
    password = f.get("password") or ""
    if not re.fullmatch(r"[a-z0-9._-]{3,40}", username):
        flash("Username must be 3–40 characters: letters, digits, dot, dash or underscore.", "error")
        return redirect(url_for("lot_detail", lot_id=lot_id))
    if len(password) < 6:
        flash("Password must be at least 6 characters.", "error")
        return redirect(url_for("lot_detail", lot_id=lot_id))
    if db.query("SELECT 1 FROM staff_account WHERE username = %s", (username,), one=True):
        flash(f"Username {username} is already taken.", "error")
        return redirect(url_for("lot_detail", lot_id=lot_id))
    sid = None
    try:
        sid = db.execute("INSERT INTO staff (lot_id, full_name, designation, shift, phone) VALUES (%s, %s, %s, %s, %s)",
                         (lot_id, f["full_name"].strip(), f["designation"], f["shift"], f["phone"].strip()))
        db.execute("INSERT INTO staff_account (staff_id, username, password_hash) VALUES (%s, %s, %s)",
                   (sid, username, generate_password_hash(password, method=STAFF_HASH)))
        flash(f"{f['full_name']} added to staff and can now sign in as {username}.", "success")
    except DBError as e:
        if sid:   # don't leave an employee row without a login
            db.execute("DELETE FROM staff WHERE staff_id = %s", (sid,))
        flash(f"Staff not added: {e}", "error")
    return redirect(url_for("lot_detail", lot_id=lot_id))


@app.route("/staff/<int:staff_id>/login", methods=["POST"])
@manager_required
def toggle_staff_login(staff_id):
    acct = db.query("""SELECT sa.is_active, st.full_name, st.lot_id FROM staff_account sa
                       JOIN staff st ON st.staff_id = sa.staff_id WHERE sa.staff_id = %s""", (staff_id,), one=True)
    if not acct:
        abort(404)
    if staff_id == g.user["staff_id"]:
        flash("You cannot disable your own login.", "error")
    else:
        new = 0 if acct["is_active"] else 1
        db.execute("UPDATE staff_account SET is_active = %s WHERE staff_id = %s", (new, staff_id))
        flash(f"{acct['full_name']} can {'now' if new else 'no longer'} sign in.", "success")
    return redirect(url_for("lot_detail", lot_id=acct["lot_id"]))


# --------------------------------------------------------------------------
# reports
# --------------------------------------------------------------------------
@app.route("/mongodb")
def mongodb_page():
    """Hybrid view: MongoDB collections, nested queries, and SQL + MongoDB combined by lot_id."""
    # SQL half of the combined table
    sql_rows = db.query("""SELECT pl.lot_id, pl.lot_name,
                                  (SELECT COUNT(*) FROM parking_slot sl WHERE sl.lot_id = pl.lot_id) AS slots,
                                  fn_occupancy_percent(pl.lot_id) AS occupancy,
                                  COALESCE(r.total_revenue, 0) AS revenue
                           FROM parking_lot pl
                           LEFT JOIN vw_revenue_per_lot r ON r.lot_id = pl.lot_id
                           ORDER BY pl.lot_id""")
    ctx = {"sql_rows": sql_rows, "mongo_error": None}
    try:
        profiles = mongo.lot_profiles()
        ratings = mongo.rating_summary()
        db_ = mongo.get_db()
        ctx["counts"] = {"lot_profiles": db_.lot_profiles.count_documents({}),
                         "reviews": db_.reviews.count_documents({})}
        ctx["sample_profile"] = json.dumps(mongo.sample_document("lot_profiles", "lot_id", 1),
                                           indent=2, default=str, ensure_ascii=False)
        ctx["sample_review"] = json.dumps(mongo.sample_document("reviews", "session_id", 2),
                                          indent=2, default=str, ensure_ascii=False)
        ctx["queries"] = [dict(q, rows=mongo.run_nested(q)) for q in mongo.NESTED_QUERIES]
        for r in sql_rows:   # application-level join on lot_id
            p_ = profiles.get(r["lot_id"], {})
            rt = ratings.get(r["lot_id"], {})
            r["chargers"] = len(p_.get("ev_chargers", []))
            r["open_24h"] = (p_.get("opening_hours") or {}).get("open_24h")
            r["avg_rating"] = rt.get("avg_rating")
            r["reviews"] = rt.get("reviews", 0)
    except MongoUnavailable as e:
        ctx["mongo_error"] = str(e)
    return render_template("mongodb.html", **ctx)


@app.route("/reports")
def reports():
    results = []
    for code, title, concept, sql in REPORT_QUERIES:
        try:
            cols, rows = db.query_with_columns(sql.strip())
            results.append(dict(code=code, title=title, concept=concept, sql=sql.strip(),
                                cols=cols, rows=rows, error=None))
        except DBError as e:
            results.append(dict(code=code, title=title, concept=concept, sql=sql.strip(),
                                cols=[], rows=[], error=str(e)))
    return render_template("reports.html", results=results)


@app.errorhandler(404)
def not_found(_e):
    return render_template("message.html", title="Not found",
                           message="That record does not exist."), 404


@app.errorhandler(DBError)
def db_error(e):
    return render_template("message.html", title="Database error", message=str(e)), 500


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1",
            host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", "5000")))
