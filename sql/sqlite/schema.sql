-- =====================================================================
-- SMART PARKING MANAGEMENT SYSTEM — SQLite demo edition
-- Same 10 tables, sample data, views and rules as the MySQL scripts, so
-- the app runs with zero setup. SQLite has no stored procedures or ENUM:
-- procedures are mirrored in db.py and ENUMs become CHECK constraints.
-- =====================================================================
PRAGMA foreign_keys = ON;

CREATE TABLE parking_lot (
    lot_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    lot_name        VARCHAR(60)  NOT NULL UNIQUE,
    location        VARCHAR(120) NOT NULL,
    total_floors    INT NOT NULL DEFAULT 1 CHECK (total_floors > 0),
    contact_number  VARCHAR(15)  NOT NULL
);

CREATE TABLE customer (
    customer_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name       VARCHAR(60)  NOT NULL,
    email           VARCHAR(80)  NOT NULL UNIQUE,
    phone           VARCHAR(15)  NOT NULL UNIQUE,
    password_hash   VARCHAR(255) NOT NULL,
    registered_on   DATE NOT NULL DEFAULT (CURRENT_DATE)
);

CREATE TABLE staff (
    staff_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    lot_id          INT NOT NULL REFERENCES parking_lot(lot_id) ON DELETE CASCADE ON UPDATE CASCADE,
    full_name       VARCHAR(60) NOT NULL,
    designation     TEXT NOT NULL CHECK (designation IN ('Manager','Attendant','Security')),
    shift           TEXT NOT NULL CHECK (shift IN ('Morning','Evening','Night')),
    phone           VARCHAR(15) NOT NULL UNIQUE
);

CREATE TABLE parking_slot (
    slot_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    lot_id            INT NOT NULL REFERENCES parking_lot(lot_id) ON DELETE CASCADE ON UPDATE CASCADE,
    slot_number       VARCHAR(10) NOT NULL,
    floor_number      INT NOT NULL DEFAULT 1 CHECK (floor_number > 0),
    slot_type         TEXT NOT NULL DEFAULT 'Car' CHECK (slot_type IN ('Car','Bike','EV','Handicap')),
    under_maintenance INTEGER NOT NULL DEFAULT 0 CHECK (under_maintenance IN (0,1)),
    UNIQUE (lot_id, slot_number)
);

CREATE TABLE vehicle (
    vehicle_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id     INT NOT NULL REFERENCES customer(customer_id) ON DELETE RESTRICT ON UPDATE CASCADE,
    vehicle_number  VARCHAR(15) NOT NULL UNIQUE,
    vehicle_type    TEXT NOT NULL CHECK (vehicle_type IN ('Car','Bike','EV','Handicap')),
    model_name      VARCHAR(40)
);

CREATE TABLE parking_rate (
    rate_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    lot_id          INT NOT NULL REFERENCES parking_lot(lot_id) ON DELETE CASCADE ON UPDATE CASCADE,
    vehicle_type    TEXT NOT NULL CHECK (vehicle_type IN ('Car','Bike','EV','Handicap')),
    rate_per_hour   DECIMAL(6,2) NOT NULL CHECK (rate_per_hour > 0),
    UNIQUE (lot_id, vehicle_type)
);

CREATE TABLE booking (
    booking_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    vehicle_id      INT NOT NULL REFERENCES vehicle(vehicle_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    slot_id         INT NOT NULL REFERENCES parking_slot(slot_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    start_time      DATETIME NOT NULL,
    end_time        DATETIME NOT NULL,
    booking_status  TEXT NOT NULL DEFAULT 'Confirmed' CHECK (booking_status IN ('Confirmed','Cancelled','Completed')),
    confirmed_slot  INT GENERATED ALWAYS AS (CASE WHEN booking_status = 'Confirmed' THEN slot_id END) STORED,
    CHECK (end_time > start_time)
);
CREATE UNIQUE INDEX uq_one_confirmed_booking_per_slot ON booking(confirmed_slot);

CREATE TABLE parking_session (
    session_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    booking_id      INT NULL UNIQUE REFERENCES booking(booking_id) ON DELETE SET NULL ON UPDATE CASCADE,
    vehicle_id      INT NOT NULL REFERENCES vehicle(vehicle_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    slot_id         INT NOT NULL REFERENCES parking_slot(slot_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    entry_time      DATETIME NOT NULL,
    exit_time       DATETIME NULL,
    amount_due      DECIMAL(8,2) NULL CHECK (amount_due IS NULL OR amount_due >= 0),
    session_status  TEXT GENERATED ALWAYS AS (CASE WHEN exit_time IS NULL THEN 'Active' ELSE 'Completed' END) STORED,
    total_hours     REAL GENERATED ALWAYS AS (
                        ROUND(CAST(ROUND((julianday(exit_time) - julianday(entry_time)) * 1440) AS INTEGER) / 60.0, 2)) STORED,
    active_slot     INT GENERATED ALWAYS AS (CASE WHEN exit_time IS NULL THEN slot_id END) STORED,
    active_vehicle  INT GENERATED ALWAYS AS (CASE WHEN exit_time IS NULL THEN vehicle_id END) STORED,
    CHECK (exit_time IS NULL OR exit_time >= entry_time)
);
CREATE UNIQUE INDEX uq_one_car_per_slot ON parking_session(active_slot);
CREATE UNIQUE INDEX uq_one_slot_per_car ON parking_session(active_vehicle);

CREATE TABLE payment (
    payment_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      INT NOT NULL UNIQUE REFERENCES parking_session(session_id) ON DELETE RESTRICT ON UPDATE CASCADE,
    payment_mode    TEXT NOT NULL CHECK (payment_mode IN ('Cash','Card','UPI','Wallet')),
    payment_date    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    payment_status  TEXT NOT NULL DEFAULT 'Paid' CHECK (payment_status IN ('Paid','Pending','Refunded'))
);

CREATE TABLE staff_account (
    staff_id        INTEGER PRIMARY KEY REFERENCES staff(staff_id) ON DELETE CASCADE ON UPDATE CASCADE,
    username        VARCHAR(40)  NOT NULL UNIQUE,
    password_hash   VARCHAR(255) NOT NULL,
    is_active       INTEGER      NOT NULL DEFAULT 1,
    last_login      DATETIME     NULL
);

CREATE INDEX idx_session_entry ON parking_session(entry_time);
CREATE INDEX idx_booking_start ON booking(start_time);
CREATE INDEX idx_payment_date  ON payment(payment_date);

-- ----------------------------- SAMPLE DATA ---------------------------
INSERT INTO parking_lot (lot_name, location, total_floors, contact_number) VALUES
('Central Mall Parking',    'MG Road, Bengaluru',    3, '9845012345'),
('Tech Park Parking',       'Whitefield, Bengaluru', 2, '9845098765'),
('Railway Station Parking', 'City Railway Station',  1, '9845011122');

INSERT INTO customer (full_name, email, phone, password_hash, registered_on) VALUES
('Rohan Sharma',   'rohan.sharma@mail.com', '9900011111', 'hash_pw_1', '2025-01-10'),
('Ananya Iyer',    'ananya.iyer@mail.com',  '9900022222', 'hash_pw_2', '2025-01-15'),
('Vikram Rao',     'vikram.rao@mail.com',   '9900033333', 'hash_pw_3', '2025-02-02'),
('Sneha Kulkarni', 'sneha.k@mail.com',      '9900044444', 'hash_pw_4', '2025-02-20'),
('Arjun Mehta',    'arjun.mehta@mail.com',  '9900055555', 'hash_pw_5', '2025-03-05'),
('Priya Nair',     'priya.nair@mail.com',   '9900066666', 'hash_pw_6', '2025-03-18'),
('Karan Verma',    'karan.verma@mail.com',  '9900077777', 'hash_pw_7', '2025-04-01'),
('Divya Reddy',    'divya.reddy@mail.com',  '9900088888', 'hash_pw_8', '2025-04-12');

INSERT INTO staff (lot_id, full_name, designation, shift, phone) VALUES
(1, 'Suresh Kumar', 'Manager',   'Morning', '9880011111'),
(1, 'Manoj Pillai', 'Attendant', 'Evening', '9880022222'),
(2, 'Ravi Teja',    'Manager',   'Morning', '9880033333'),
(2, 'Ganesh Naik',  'Security',  'Night',   '9880044444'),
(3, 'Lakshmi Devi', 'Attendant', 'Morning', '9880055555');

INSERT INTO parking_slot (lot_id, slot_number, floor_number, slot_type, under_maintenance) VALUES
(1,'A1',1,'Car',0),(1,'A2',1,'Car',0),(1,'A3',1,'Car',0),
(1,'A4',1,'Handicap',0),(1,'B1',2,'Bike',0),(1,'B2',2,'Bike',0),
(1,'B3',2,'EV',0),(1,'C1',3,'Car',1),
(2,'T1',1,'Car',0),(2,'T2',1,'Car',0),(2,'T3',1,'EV',0),
(2,'T4',2,'Bike',0),(2,'T5',2,'Car',0),
(3,'R1',1,'Car',0),(3,'R2',1,'Bike',0),(3,'R3',1,'Car',0),
(3,'R4',1,'Handicap',0);

INSERT INTO vehicle (customer_id, vehicle_number, vehicle_type, model_name) VALUES
(1, 'KA01AB1234', 'Car',      'Hyundai Creta'),
(2, 'KA02CD5678', 'Bike',     'Royal Enfield Classic'),
(3, 'KA03EF9012', 'Car',      'Maruti Swift'),
(4, 'KA04GH3456', 'EV',       'Tata Nexon EV'),
(5, 'KA05IJ7890', 'Car',      'Honda City'),
(6, 'KA06KL2345', 'Bike',     'TVS Jupiter'),
(7, 'KA07MN6789', 'Car',      'Toyota Innova'),
(8, 'KA08OP0123', 'Handicap', 'Maruti Wagon R (Modified)');

INSERT INTO parking_rate (lot_id, vehicle_type, rate_per_hour) VALUES
(1,'Car',40.00),(1,'Bike',15.00),(1,'EV',30.00),(1,'Handicap',20.00),
(2,'Car',35.00),(2,'Bike',10.00),(2,'EV',25.00),(2,'Handicap',15.00),
(3,'Car',30.00),(3,'Bike',10.00),(3,'EV',25.00),(3,'Handicap',15.00);

INSERT INTO booking (vehicle_id, slot_id, start_time, end_time, booking_status) VALUES
(1, 2,  '2026-08-20 09:00:00', '2026-08-20 13:00:00', 'Completed'),
(4, 7,  '2026-12-05 10:00:00', '2026-12-05 18:00:00', 'Confirmed'),
(7, 9,  '2026-08-22 08:30:00', '2026-08-22 20:00:00', 'Completed'),
(2, 6,  '2026-08-23 11:00:00', '2026-08-23 15:00:00', 'Cancelled');

INSERT INTO parking_session (booking_id, vehicle_id, slot_id, entry_time, exit_time, amount_due) VALUES
(1,    1, 2,  '2026-08-20 09:05:00', '2026-08-20 13:10:00', 163.20),
(3,    7, 9,  '2026-08-22 08:35:00', '2026-08-22 19:50:00', 393.75),
(NULL, 3, 14, '2026-08-24 09:00:00', '2026-08-24 12:30:00', 105.00),
(NULL, 5, 9,  '2026-08-24 14:00:00', NULL, NULL),
(NULL, 6, 15, '2026-08-24 15:30:00', NULL, NULL),
(NULL, 2, 6,  '2026-08-25 08:00:00', '2026-08-25 09:45:00', 26.25);

INSERT INTO payment (session_id, payment_mode, payment_date, payment_status) VALUES
(1, 'UPI',    '2026-08-20 13:12:00', 'Paid'),
(2, 'Card',   '2026-08-22 19:52:00', 'Paid'),
(3, 'Cash',   '2026-08-24 12:32:00', 'Paid'),
(6, 'Wallet', '2026-08-25 09:47:00', 'Paid');

INSERT INTO staff_account (staff_id, username, password_hash) VALUES
(1, 'suresh.kumar', 'pbkdf2:sha256:100000$hNkTTuKUXIZD68X2$122ebd5415f2efddb728edb2a46787e0d1601bd439dfdc493467e3c3f3362490'),
(2, 'manoj.pillai', 'pbkdf2:sha256:100000$TEFOtG0DcIQEbgUd$72bcd772331f848848575414fca3f50ee0be7850cf26777e2341033296ff82cd'),
(3, 'ravi.teja', 'pbkdf2:sha256:100000$p3ti2IhRmVB74qlT$adc5229e6223d1be0fcd371c444a8ede554d2f641ab54c7d997bca3795feea15'),
(4, 'ganesh.naik', 'pbkdf2:sha256:100000$2BZCNrcmCseBV450$cb2a47a1d0ce12163c2b4d342c9b0bd3084e5fcdb62a2ef42480d96afe9f6d37'),
(5, 'lakshmi.devi', 'pbkdf2:sha256:100000$QsqSp3dGxF0JiCDU$a9ba4ce819c492407d0307abd74f516967c1f630eac219b6da98603ce376485f');

-- ------------------------------- VIEWS -------------------------------
CREATE VIEW vw_slot_status AS
SELECT
    sl.slot_id, sl.lot_id, sl.slot_number, sl.floor_number, sl.slot_type, sl.under_maintenance,
    CASE
        WHEN sl.under_maintenance = 1 THEN 'Maintenance'
        WHEN s.session_id IS NOT NULL THEN 'Occupied'
        WHEN b.booking_id IS NOT NULL THEN 'Reserved'
        ELSE 'Available'
    END              AS status,
    s.session_id     AS active_session_id,
    s.vehicle_id     AS parked_vehicle_id,
    b.booking_id     AS confirmed_booking_id
FROM parking_slot sl
LEFT JOIN parking_session s ON s.active_slot    = sl.slot_id
LEFT JOIN booking b         ON b.confirmed_slot = sl.slot_id;

CREATE VIEW vw_slot_availability AS
SELECT pl.lot_id, pl.lot_name, ss.slot_type,
       COUNT(*) AS total_slots,
       SUM(CASE WHEN ss.status = 'Available' THEN 1 ELSE 0 END) AS available_slots,
       SUM(CASE WHEN ss.status = 'Occupied'  THEN 1 ELSE 0 END) AS occupied_slots,
       SUM(CASE WHEN ss.status = 'Reserved'  THEN 1 ELSE 0 END) AS reserved_slots
FROM vw_slot_status ss JOIN parking_lot pl ON pl.lot_id = ss.lot_id
GROUP BY pl.lot_id, pl.lot_name, ss.slot_type;

CREATE VIEW vw_active_sessions AS
SELECT s.session_id, v.vehicle_number, v.vehicle_type,
       c.full_name AS customer_name, pl.lot_name, sl.slot_number, s.entry_time
FROM parking_session s
JOIN vehicle v       ON v.vehicle_id = s.vehicle_id
JOIN customer c      ON c.customer_id = v.customer_id
JOIN parking_slot sl ON sl.slot_id = s.slot_id
JOIN parking_lot pl  ON pl.lot_id = sl.lot_id
WHERE s.exit_time IS NULL;

CREATE VIEW vw_revenue_per_lot AS
SELECT pl.lot_id, pl.lot_name,
       COUNT(p.payment_id) AS total_transactions,
       SUM(s.amount_due)   AS total_revenue
FROM payment p
JOIN parking_session s ON s.session_id = p.session_id
JOIN parking_slot sl   ON sl.slot_id = s.slot_id
JOIN parking_lot pl    ON pl.lot_id = sl.lot_id
WHERE p.payment_status = 'Paid'
GROUP BY pl.lot_id, pl.lot_name;

-- ------------------------------ TRIGGERS -----------------------------
-- 1. New booking: free slot of the right type
CREATE TRIGGER trg_before_booking_insert
BEFORE INSERT ON booking
WHEN NEW.booking_status = 'Confirmed'
BEGIN
    SELECT RAISE(ABORT, 'Cannot book a slot that is under maintenance')
    WHERE (SELECT under_maintenance FROM parking_slot WHERE slot_id = NEW.slot_id) = 1;
    SELECT RAISE(ABORT, 'Slot is already occupied or reserved')
    WHERE EXISTS (SELECT 1 FROM parking_session WHERE active_slot = NEW.slot_id)
       OR EXISTS (SELECT 1 FROM booking WHERE confirmed_slot = NEW.slot_id);
    SELECT RAISE(ABORT, 'Slot type does not match vehicle type')
    WHERE (SELECT slot_type FROM parking_slot WHERE slot_id = NEW.slot_id)
       <> (SELECT vehicle_type FROM vehicle WHERE vehicle_id = NEW.vehicle_id);
END;

-- 2. Closed bookings cannot be reopened or moved
CREATE TRIGGER trg_before_booking_update
BEFORE UPDATE ON booking
BEGIN
    SELECT RAISE(ABORT, 'A closed booking cannot be reopened')
    WHERE OLD.booking_status <> 'Confirmed' AND NEW.booking_status <> OLD.booking_status;
    SELECT RAISE(ABORT, 'Cancel the booking and make a new one instead')
    WHERE NEW.vehicle_id <> OLD.vehicle_id OR NEW.slot_id <> OLD.slot_id;
END;

-- 3. Entry: booked vehicle/slot must match; free slot of the right type
CREATE TRIGGER trg_before_session_insert
BEFORE INSERT ON parking_session
BEGIN
    SELECT RAISE(ABORT, 'Session must use the booked vehicle and slot')
    WHERE NEW.booking_id IS NOT NULL AND EXISTS (
        SELECT 1 FROM booking WHERE booking_id = NEW.booking_id
        AND (vehicle_id <> NEW.vehicle_id OR slot_id <> NEW.slot_id));
    SELECT RAISE(ABORT, 'Only confirmed bookings can be checked in')
    WHERE NEW.exit_time IS NULL AND NEW.booking_id IS NOT NULL
      AND (SELECT booking_status FROM booking WHERE booking_id = NEW.booking_id) <> 'Confirmed';
    SELECT RAISE(ABORT, 'Slot is under maintenance')
    WHERE NEW.exit_time IS NULL
      AND (SELECT under_maintenance FROM parking_slot WHERE slot_id = NEW.slot_id) = 1;
    SELECT RAISE(ABORT, 'Slot type does not match vehicle type')
    WHERE NEW.exit_time IS NULL
      AND (SELECT slot_type FROM parking_slot WHERE slot_id = NEW.slot_id)
       <> (SELECT vehicle_type FROM vehicle WHERE vehicle_id = NEW.vehicle_id);
    SELECT RAISE(ABORT, 'This vehicle is already parked')
    WHERE NEW.exit_time IS NULL
      AND EXISTS (SELECT 1 FROM parking_session WHERE active_vehicle = NEW.vehicle_id);
    SELECT RAISE(ABORT, 'Slot is already occupied')
    WHERE NEW.exit_time IS NULL
      AND EXISTS (SELECT 1 FROM parking_session WHERE active_slot = NEW.slot_id);
    SELECT RAISE(ABORT, 'Slot is reserved for another booking')
    WHERE NEW.exit_time IS NULL
      AND EXISTS (SELECT 1 FROM booking WHERE confirmed_slot = NEW.slot_id
                  AND booking_id <> IFNULL(NEW.booking_id, 0));
END;

-- 4a. A finished session cannot be edited; vehicle/slot/entry never change
CREATE TRIGGER trg_before_session_update
BEFORE UPDATE OF vehicle_id, slot_id, entry_time, exit_time ON parking_session
BEGIN
    SELECT RAISE(ABORT, 'Vehicle, slot and entry time cannot be changed')
    WHERE NEW.vehicle_id <> OLD.vehicle_id OR NEW.slot_id <> OLD.slot_id
       OR NEW.entry_time <> OLD.entry_time;
    SELECT RAISE(ABORT, 'A completed session cannot be changed')
    WHERE OLD.exit_time IS NOT NULL
      AND (NEW.exit_time IS NULL OR NEW.exit_time <> OLD.exit_time);
END;

-- 4b. Billing on exit (SQLite cannot assign NEW.* in a BEFORE trigger,
--     so the amount is written by this AFTER trigger)
CREATE TRIGGER trg_session_bill
AFTER UPDATE OF exit_time ON parking_session
WHEN NEW.exit_time IS NOT NULL AND OLD.exit_time IS NULL
BEGIN
    UPDATE parking_session
    SET amount_due = ROUND(MAX(NEW.total_hours, 1.0) * (
            SELECT pr.rate_per_hour FROM parking_rate pr
            JOIN parking_slot sl ON sl.lot_id = pr.lot_id
            JOIN vehicle v ON v.vehicle_type = pr.vehicle_type
            WHERE sl.slot_id = NEW.slot_id AND v.vehicle_id = NEW.vehicle_id), 2)
    WHERE session_id = NEW.session_id;
    -- 5. a pre-booked stay completes its booking
    UPDATE booking SET booking_status = 'Completed'
    WHERE booking_id = NEW.booking_id AND NEW.booking_id IS NOT NULL;
END;

-- 4c. The bill cannot be edited once set
CREATE TRIGGER trg_before_amount_update
BEFORE UPDATE OF amount_due ON parking_session
WHEN OLD.amount_due IS NOT NULL
BEGIN
    SELECT RAISE(ABORT, 'A completed session cannot be changed');
END;

-- 6. Only a finished stay can be paid
CREATE TRIGGER trg_before_payment_insert
BEFORE INSERT ON payment
BEGIN
    SELECT RAISE(ABORT, 'Only a completed session can be paid')
    WHERE NOT EXISTS (SELECT 1 FROM parking_session
                      WHERE session_id = NEW.session_id AND exit_time IS NOT NULL);
END;
