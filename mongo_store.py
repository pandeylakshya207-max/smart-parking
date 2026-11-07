"""MongoDB side of the hybrid design.

SQL (MySQL) keeps everything that must be exact and linked: customers,
vehicles, slots, sessions, bills, payments. MongoDB keeps data whose
shape varies from lot to lot, or that is free text:

  lot_profiles  one document per lot, with NESTED data that differs
                between lots: opening hours, amenities, EV chargers
                (each with its own connector / power / slot).
  reviews       one document per paid visit: rating, comment, tags and
                nested aspect scores.

The two databases are joined in the application by lot_id and
session_id (an "application-level join").

Connection, chosen with the MONGO_URI environment variable:
  MONGO_URI=mongodb://localhost:27017   real MongoDB (laptop or Atlas)
  (not set) or MONGO_URI=memory         in-memory MongoDB (mongomock) for
                                        the zero-setup demo
If a real server cannot be reached, MongoDB features show "unavailable"
and every SQL feature keeps working (see report, "What if one fails").
"""
import os
from datetime import datetime

MONGO_URI = os.environ.get("MONGO_URI", "memory").strip()
MONGO_DB = os.environ.get("MONGO_DB", "smart_parking")

_client = None
_db = None
_error = None
_mode = None          # "server" | "memory" | "offline"


class MongoUnavailable(Exception):
    """Raised when MongoDB cannot be reached; callers show a notice instead."""


# ---------------------------------------------------------------- sample documents
LOT_PROFILES = [
    {
        "lot_id": 1, "lot_name": "Central Mall Parking",
        "description": "Covered multi-level parking under Central Mall.",
        "opening_hours": {"weekdays": {"open": "07:00", "close": "23:30"},
                          "weekends": {"open": "07:00", "close": "23:59"}, "open_24h": False},
        "amenities": ["CCTV", "Covered", "Washroom", "Wheelchair ramp", "Car wash"],
        "ev_chargers": [
            {"charger_id": "CM-EV1", "slot_number": "B3", "connector": "CCS2", "power_kw": 60, "network": "Tata Power"},
            {"charger_id": "CM-EV2", "slot_number": "B3", "connector": "Type 2", "power_kw": 22, "network": "Tata Power"},
        ],
        "security": {"guards_per_shift": 2, "cctv_cameras": 48},
    },
    {
        "lot_id": 2, "lot_name": "Tech Park Parking",
        "description": "Open-air and basement parking for the Whitefield tech park.",
        "opening_hours": {"weekdays": {"open": "00:00", "close": "23:59"},
                          "weekends": {"open": "00:00", "close": "23:59"}, "open_24h": True},
        "amenities": ["CCTV", "24x7 security", "EV charging", "Bicycle stand"],
        "ev_chargers": [
            {"charger_id": "TP-EV1", "slot_number": "T3", "connector": "CCS2", "power_kw": 30, "network": "Statiq"},
        ],
        "security": {"guards_per_shift": 3, "cctv_cameras": 30},
    },
    {
        "lot_id": 3, "lot_name": "Railway Station Parking",
        "description": "Surface parking next to the main railway station entrance.",
        "opening_hours": {"weekdays": {"open": "04:00", "close": "23:59"},
                          "weekends": {"open": "04:00", "close": "23:59"}, "open_24h": False},
        "amenities": ["CCTV", "Porter service"],
        "ev_chargers": [],
        "security": {"guards_per_shift": 1, "cctv_cameras": 12},
    },
]

REVIEWS = [   # one per paid sample session (session_id is unique)
    {"session_id": 1, "lot_id": 1, "vehicle_number": "KA01AB1234", "rating": 4,
     "comment": "Easy to find a slot, clear signs on every floor.",
     "tags": ["clean", "well-lit"], "aspects": {"safety": 5, "cleanliness": 4, "ease_of_parking": 4},
     "created_at": datetime(2026, 8, 20, 13, 20)},
    {"session_id": 2, "lot_id": 2, "vehicle_number": "KA07MN6789", "rating": 5,
     "comment": "Guards were helpful and the lot felt very safe all day.",
     "tags": ["safe", "helpful staff"], "aspects": {"safety": 5, "cleanliness": 4, "ease_of_parking": 5},
     "created_at": datetime(2026, 8, 22, 20, 5)},
    {"session_id": 3, "lot_id": 3, "vehicle_number": "KA03EF9012", "rating": 3,
     "comment": "Convenient for the station but crowded in the morning.",
     "tags": ["crowded"], "aspects": {"safety": 3, "cleanliness": 3, "ease_of_parking": 2},
     "created_at": datetime(2026, 8, 24, 12, 40)},
    {"session_id": 6, "lot_id": 1, "vehicle_number": "KA02CD5678", "rating": 5,
     "comment": "Separate bike floor, no waiting.",
     "tags": ["safe", "quick exit"], "aspects": {"safety": 5, "cleanliness": 5, "ease_of_parking": 5},
     "created_at": datetime(2026, 8, 25, 9, 55)},
]

# ---------------------------------------------------------------- nested queries shown in the app/report
NESTED_QUERIES = [
    {
        "code": "M1", "title": "Lots with a fast CCS2 charger (50 kW or more)",
        "concept": "Query inside an array of sub-documents ($elemMatch)",
        "collection": "lot_profiles",
        "query": '{ "ev_chargers": { "$elemMatch": { "connector": "CCS2", "power_kw": { "$gte": 50 } } } }',
        "filter": {"ev_chargers": {"$elemMatch": {"connector": "CCS2", "power_kw": {"$gte": 50}}}},
        "projection": {"_id": 0, "lot_id": 1, "lot_name": 1, "ev_chargers.charger_id": 1,
                       "ev_chargers.connector": 1, "ev_chargers.power_kw": 1},
    },
    {
        "code": "M2", "title": "Lots open 24 hours",
        "concept": "Dot notation into a nested object",
        "collection": "lot_profiles",
        "query": '{ "opening_hours.open_24h": true }',
        "filter": {"opening_hours.open_24h": True},
        "projection": {"_id": 0, "lot_id": 1, "lot_name": 1, "opening_hours.weekdays": 1},
    },
    {
        "code": "M3", "title": "Reviews tagged \"safe\" with a safety score of 5",
        "concept": "Array match + nested field filter",
        "collection": "reviews",
        "query": '{ "tags": "safe", "aspects.safety": { "$gte": 5 } }',
        "filter": {"tags": "safe", "aspects.safety": {"$gte": 5}},
        "projection": {"_id": 0, "session_id": 1, "lot_id": 1, "rating": 1, "tags": 1, "aspects.safety": 1},
    },
    {
        "code": "M4", "title": "Average rating and safety score per lot",
        "concept": "Aggregation pipeline ($group, $avg)",
        "collection": "reviews",
        "query": '[ { "$group": { "_id": "$lot_id", "reviews": { "$sum": 1 }, '
                 '"avg_rating": { "$avg": "$rating" }, "avg_safety": { "$avg": "$aspects.safety" } } }, '
                 '{ "$sort": { "_id": 1 } } ]',
        "pipeline": [{"$group": {"_id": "$lot_id", "reviews": {"$sum": 1}, "avg_rating": {"$avg": "$rating"},
                                 "avg_safety": {"$avg": "$aspects.safety"}}},
                     {"$sort": {"_id": 1}}],
    },
]


# ---------------------------------------------------------------- connection
def _seed(db):
    if db.lot_profiles.count_documents({}) == 0:
        db.lot_profiles.insert_many([dict(d) for d in LOT_PROFILES])
    if db.reviews.count_documents({}) == 0:
        db.reviews.insert_many([dict(d) for d in REVIEWS])
    # one profile per lot, one review per visit: no duplicate documents
    db.lot_profiles.create_index("lot_id", unique=True)
    db.reviews.create_index("session_id", unique=True)
    db.reviews.create_index("lot_id")


def get_db():
    """Return the MongoDB database, or raise MongoUnavailable."""
    global _client, _db, _error, _mode
    if _db is not None:
        return _db
    if _mode == "offline":
        raise MongoUnavailable(_error)
    try:
        if MONGO_URI in ("", "memory", "mock"):
            import mongomock
            _client = mongomock.MongoClient()
            _mode = "memory"
        else:
            import pymongo
            _client = pymongo.MongoClient(MONGO_URI, serverSelectionTimeoutMS=2500)
            _client.admin.command("ping")
            _mode = "server"
        _db = _client[MONGO_DB]
        _seed(_db)
        return _db
    except Exception as e:                       # server down, wrong URI, driver missing
        _mode, _error, _db = "offline", f"{type(e).__name__}: {str(e)[:160]}", None
        raise MongoUnavailable(_error)


def reset(uri=None):
    """Forget the connection (used by tests and after a failure)."""
    global _client, _db, _error, _mode, MONGO_URI
    if uri is not None:
        MONGO_URI = uri
    _client = _db = _error = _mode = None


def status_label():
    try:
        get_db()
    except MongoUnavailable:
        pass
    return {"server": "MongoDB · connected", "memory": "MongoDB · in-memory demo",
            "offline": "MongoDB · offline"}.get(_mode, "MongoDB")


def is_up():
    try:
        get_db()
        return True
    except MongoUnavailable:
        return False


def last_error():
    return _error


# ---------------------------------------------------------------- data access
def _clean(doc):
    if doc is None:
        return None
    doc = dict(doc)
    doc.pop("_id", None)
    return doc


def lot_profile(lot_id):
    return _clean(get_db().lot_profiles.find_one({"lot_id": lot_id}))


def lot_profiles():
    return {d["lot_id"]: _clean(d) for d in get_db().lot_profiles.find({})}


def reviews_for_lot(lot_id, limit=5):
    cur = get_db().reviews.find({"lot_id": lot_id}).sort("created_at", -1).limit(limit)
    return [_clean(d) for d in cur]


def review_for_session(session_id):
    return _clean(get_db().reviews.find_one({"session_id": session_id}))


def rating_summary():
    """{lot_id: {"reviews": n, "avg_rating": x, "avg_safety": y}} via aggregation."""
    out = {}
    for row in get_db().reviews.aggregate(NESTED_QUERIES[3]["pipeline"]):
        out[row["_id"]] = {"reviews": row["reviews"], "avg_rating": round(row["avg_rating"], 2),
                           "avg_safety": round(row["avg_safety"], 2)}
    return out


def add_review(session_id, lot_id, vehicle_number, rating, comment, tags, aspects):
    doc = {"session_id": session_id, "lot_id": lot_id, "vehicle_number": vehicle_number,
           "rating": rating, "comment": comment, "tags": tags, "aspects": aspects,
           "created_at": datetime.now().replace(microsecond=0)}
    get_db().reviews.insert_one(doc)       # unique index on session_id: one review per visit
    return _clean(doc)


def add_ev_charger(lot_id, charger):
    """$push a new sub-document into the nested ev_chargers array."""
    res = get_db().lot_profiles.update_one({"lot_id": lot_id}, {"$push": {"ev_chargers": charger}})
    return res.modified_count == 1


def run_nested(q):
    coll = get_db()[q["collection"]]
    if "pipeline" in q:
        return [dict(r) for r in coll.aggregate(q["pipeline"])]
    return [_clean(d) for d in coll.find(q["filter"], q.get("projection"))]


def sample_document(collection, key, value):
    return _clean(get_db()[collection].find_one({key: value}))
