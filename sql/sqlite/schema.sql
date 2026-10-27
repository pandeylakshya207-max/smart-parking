-- =====================================================================
-- SMART PARKING MANAGEMENT SYSTEM — SQLite demo edition
-- Same 9 tables, sample data, views and trigger behaviour as the MySQL
-- scripts, so the app can run with zero setup. SQLite has no stored
-- procedures or ENUM; procedures are mirrored in db.py and ENUMs become
-- CHECK constraints.
-- =====================================================================
PRAGMA foreign_keys = ON;

CREATE TABLE parking_lot (
    lot_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    lot_name        VARCHAR(60)  NOT NULL,
    location        VARCHAR(120) NOT NULL,
    total_floors    INT NOT NULL DEFAULT 1,
    total_slots     INT NOT NULL CHECK (total_slots > 0),
    contact_number  VARCHAR(15) NOT NULL
);

CREATE TABLE customer (
    customer_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name       VARCHAR(60) NOT NULL,
    email           VARCHAR(80) UNIQUE NOT NULL,
    phone           VARCHAR(15) UNIQUE NOT NULL,
    password_hash   VARCHAR(120) NOT NULL,
    registered_on   DATE NOT NULL DEFAULT (CURRENT_DATE)
);

CREATE TABLE staff (
    staff_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    lot_id          INT NOT NULL REFERENCES parking_lot(lot_id) ON DELETE CASCADE ON UPDATE CASCADE,
    full_name       VARCHAR(60) NOT NULL,
    designation     VARCHAR(30) NOT NULL,
    shift           TEXT NOT NULL CHECK (shift IN ('Morning','Evening','Night')),
    phone           VARCHAR(15) NOT NULL
);

CREATE TABLE parking_slot (
    slot_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    lot_id          INT NOT NULL REFERENCES parking_lot(lot_id) ON DELETE CASCADE ON UPDATE CASCADE,
    slot_number     VARCHAR(10) NOT NULL,
    floor_number    INT NOT NULL DEFAULT 1,
    slot_type       TEXT NOT NULL DEFAULT 'Car' CHECK (slot_type IN ('Car','Bike','EV','Handicap')),
    status          TEXT NOT NULL DEFAULT 'Available' CHECK (status IN ('Available','Occupied','Reserved','Maintenance')),
    UNIQUE (lot_id, slot_number)
);

CREATE TABLE vehicle (
    vehicle_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id     INT NOT NULL REFERENCES customer(customer_id) ON DELETE CASCADE ON UPDATE CASCADE,
    vehicle_number  VARCHAR(15) UNIQUE NOT NULL,
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
    customer_id     INT NOT NULL REFERENCES customer(customer_id) ON DELETE CASCADE ON UPDATE CASCADE,
    vehicle_id      INT NOT NULL REFERENCES vehicle(vehicle_id) ON DELETE CASCADE ON UPDATE CASCADE,
    slot_id         INT NOT NULL REFERENCES parking_slot(slot_id) ON DELETE CASCADE ON UPDATE CASCADE,
    booking_date    DATE NOT NULL,
    start_time      DATETIME NOT NULL,
    end_time        DATETIME NOT NULL,
    booking_status  TEXT NOT NULL DEFAULT 'Confirmed' CHECK (booking_status IN ('Confirmed','Cancelled','Completed')),
    CHECK (end_time > start_time)
);

CREATE TABLE parking_session (
    session_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    booking_id      INT NULL REFERENCES booking(booking_id) ON DELETE SET NULL ON UPDATE CASCADE,
    vehicle_id      INT NOT NULL REFERENCES vehicle(vehicle_id) ON DELETE CASCADE ON UPDATE CASCADE,
    slot_id         INT NOT NULL REFERENCES parking_slot(slot_id) ON DELETE CASCADE ON UPDATE CASCADE,
    entry_time      DATETIME NOT NULL,
    exit_time       DATETIME NULL,
    total_hours     DECIMAL(5,2) NULL,
    amount_due      DECIMAL(8,2) NULL,
    session_status  TEXT NOT NULL DEFAULT 'Active' CHECK (session_status IN ('Active','Completed'))
);

CREATE TABLE payment (
    payment_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      INT NOT NULL UNIQUE REFERENCES parking_session(session_id) ON DELETE CASCADE ON UPDATE CASCADE,
    amount_paid     DECIMAL(8,2) NOT NULL,
    payment_mode    TEXT NOT NULL CHECK (payment_mode IN ('Cash','Card','UPI','Wallet')),
    payment_date    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    payment_status  TEXT NOT NULL DEFAULT 'Paid' CHECK (payment_status IN ('Paid','Pending','Refunded'))
);

CREATE INDEX idx_slot_status    ON parking_slot(status);
CREATE INDEX idx_session_status ON parking_session(session_status);
CREATE INDEX idx_vehicle_number ON vehicle(vehicle_number);
CREATE INDEX idx_booking_date   ON booking(booking_date);

-- ----------------------------- SAMPLE DATA ---------------------------
INSERT INTO parking_lot (lot_name, location, total_floors, total_slots, contact_number) VALUES
('Central Mall Parking',   'MG Road, Bengaluru',      3, 120, '9845012345'),
('Tech Park Parking',      'Whitefield, Bengaluru',   2, 80,  '9845098765'),
('Railway Station Parking','City Railway Station',    1, 60,  '9845011122');

INSERT INTO customer (full_name, email, phone, password_hash, registered_on) VALUES
('Rohan Sharma',   'rohan.sharma@mail.com',  '9900011111', 'hash_pw_1', '2025-01-10'),
('Ananya Iyer',    'ananya.iyer@mail.com',   '9900022222', 'hash_pw_2', '2025-01-15'),
('Vikram Rao',     'vikram.rao@mail.com',    '9900033333', 'hash_pw_3', '2025-02-02'),
('Sneha Kulkarni', 'sneha.k@mail.com',       '9900044444', 'hash_pw_4', '2025-02-20'),
('Arjun Mehta',    'arjun.mehta@mail.com',   '9900055555', 'hash_pw_5', '2025-03-05'),
('Priya Nair',     'priya.nair@mail.com',    '9900066666', 'hash_pw_6', '2025-03-18'),
('Karan Verma',    'karan.verma@mail.com',   '9900077777', 'hash_pw_7', '2025-04-01'),
('Divya Reddy',    'divya.reddy@mail.com',   '9900088888', 'hash_pw_8', '2025-04-12');

INSERT INTO staff (lot_id, full_name, designation, shift, phone) VALUES
(1, 'Suresh Kumar',   'Manager',    'Morning', '9880011111'),
(1, 'Manoj Pillai',   'Attendant',  'Evening', '9880022222'),
(2, 'Ravi Teja',      'Manager',    'Morning', '9880033333'),
(2, 'Ganesh Naik',    'Security',   'Night',   '9880044444'),
(3, 'Lakshmi Devi',   'Attendant',  'Morning', '9880055555');

INSERT INTO parking_slot (lot_id, slot_number, floor_number, slot_type, status) VALUES
(1,'A1',1,'Car','Available'),(1,'A2',1,'Car','Occupied'),(1,'A3',1,'Car','Available'),
(1,'A4',1,'Handicap','Available'),(1,'B1',2,'Bike','Available'),(1,'B2',2,'Bike','Occupied'),
(1,'B3',2,'EV','Available'),(1,'C1',3,'Car','Maintenance'),
(2,'T1',1,'Car','Occupied'),(2,'T2',1,'Car','Available'),(2,'T3',1,'EV','Available'),
(2,'T4',2,'Bike','Available'),(2,'T5',2,'Car','Reserved'),
(3,'R1',1,'Car','Available'),(3,'R2',1,'Bike','Occupied'),(3,'R3',1,'Car','Available'),
(3,'R4',1,'Handicap','Available');

INSERT INTO vehicle (customer_id, vehicle_number, vehicle_type, model_name) VALUES
(1, 'KA01AB1234', 'Car',  'Hyundai Creta'),
(2, 'KA02CD5678', 'Bike', 'Royal Enfield Classic'),
(3, 'KA03EF9012', 'Car',  'Maruti Swift'),
(4, 'KA04GH3456', 'EV',   'Tata Nexon EV'),
(5, 'KA05IJ7890', 'Car',  'Honda City'),
(6, 'KA06KL2345', 'Bike', 'TVS Jupiter'),
(7, 'KA07MN6789', 'Car',  'Toyota Innova'),
(8, 'KA08OP0123', 'Handicap', 'Maruti Wagon R (Modified)');

INSERT INTO parking_rate (lot_id, vehicle_type, rate_per_hour) VALUES
(1,'Car',40.00),(1,'Bike',15.00),(1,'EV',30.00),(1,'Handicap',20.00),
(2,'Car',35.00),(2,'Bike',10.00),(2,'EV',25.00),(2,'Handicap',15.00),
(3,'Car',30.00),(3,'Bike',10.00),(3,'EV',25.00),(3,'Handicap',15.00);

INSERT INTO booking (customer_id, vehicle_id, slot_id, booking_date, start_time, end_time, booking_status) VALUES
(1, 1, 2, '2026-08-20', '2026-08-20 09:00:00', '2026-08-20 13:00:00', 'Completed'),
(4, 4, 11,'2026-08-21', '2026-08-21 10:00:00', '2026-08-21 18:00:00', 'Confirmed'),
(7, 7, 9, '2026-08-22', '2026-08-22 08:30:00', '2026-08-22 20:00:00', 'Completed'),
(2, 2, 6, '2026-08-23', '2026-08-23 11:00:00', '2026-08-23 15:00:00', 'Cancelled');

INSERT INTO parking_session (booking_id, vehicle_id, slot_id, entry_time, exit_time, total_hours, amount_due, session_status) VALUES
(1,    1, 2,  '2026-08-20 09:05:00', '2026-08-20 13:10:00', 4.08, 163.20, 'Completed'),
(3,    7, 9,  '2026-08-22 08:35:00', '2026-08-22 19:50:00', 11.25, 393.75, 'Completed'),
(NULL, 3, 14, '2026-08-24 09:00:00', '2026-08-24 12:30:00', 3.50, 105.00, 'Completed'),
(NULL, 5, 9,  '2026-08-24 14:00:00', NULL, NULL, NULL, 'Active'),
(NULL, 6, 15, '2026-08-24 15:30:00', NULL, NULL, NULL, 'Active'),
(NULL, 2, 6,  '2026-08-25 08:00:00', '2026-08-25 09:45:00', 1.75, 26.25, 'Completed');

INSERT INTO payment (session_id, amount_paid, payment_mode, payment_date, payment_status) VALUES
(1, 163.20, 'UPI',    '2026-08-20 13:12:00', 'Paid'),
(2, 393.75, 'Card',   '2026-08-22 19:52:00', 'Paid'),
(3, 105.00, 'Cash',   '2026-08-24 12:32:00', 'Paid'),
(6, 26.25,  'Wallet', '2026-08-25 09:47:00', 'Paid');

-- ------------------------------- VIEWS -------------------------------
CREATE VIEW vw_slot_availability AS
SELECT pl.lot_id, pl.lot_name, ps.slot_type,
       COUNT(*) AS total_slots,
       SUM(CASE WHEN ps.status = 'Available' THEN 1 ELSE 0 END) AS available_slots,
       SUM(CASE WHEN ps.status = 'Occupied'  THEN 1 ELSE 0 END) AS occupied_slots
FROM parking_slot ps JOIN parking_lot pl ON pl.lot_id = ps.lot_id
GROUP BY pl.lot_id, pl.lot_name, ps.slot_type;

CREATE VIEW vw_active_sessions AS
SELECT s.session_id, v.vehicle_number, v.vehicle_type,
       c.full_name AS customer_name, pl.lot_name, sl.slot_number, s.entry_time
FROM parking_session s
JOIN vehicle v       ON v.vehicle_id = s.vehicle_id
JOIN customer c      ON c.customer_id = v.customer_id
JOIN parking_slot sl ON sl.slot_id = s.slot_id
JOIN parking_lot pl  ON pl.lot_id = sl.lot_id
WHERE s.session_status = 'Active';

CREATE VIEW vw_revenue_per_lot AS
SELECT pl.lot_id, pl.lot_name,
       COUNT(p.payment_id) AS total_transactions,
       SUM(p.amount_paid)  AS total_revenue
FROM payment p
JOIN parking_session s ON s.session_id = p.session_id
JOIN parking_slot sl   ON sl.slot_id = s.slot_id
JOIN parking_lot pl    ON pl.lot_id = sl.lot_id
GROUP BY pl.lot_id, pl.lot_name;

-- ------------------------------ TRIGGERS -----------------------------
-- Vehicle enters -> slot Occupied
CREATE TRIGGER trg_after_session_insert
AFTER INSERT ON parking_session
BEGIN
    UPDATE parking_slot SET status = 'Occupied' WHERE slot_id = NEW.slot_id;
END;

-- Vehicle exits -> compute hours & bill (minimum 1 hour), complete session, free slot.
-- (SQLite cannot assign NEW.* in a BEFORE trigger, so the MySQL pair
--  trg_before_session_update + trg_after_session_exit is one AFTER trigger.)
CREATE TRIGGER trg_session_exit
AFTER UPDATE OF exit_time ON parking_session
WHEN NEW.exit_time IS NOT NULL AND OLD.exit_time IS NULL
BEGIN
    UPDATE parking_session
    SET total_hours    = ROUND((julianday(NEW.exit_time) - julianday(NEW.entry_time)) * 24.0, 2),
        amount_due     = ROUND(MAX(ROUND((julianday(NEW.exit_time) - julianday(NEW.entry_time)) * 24.0, 2), 1.0) * (
                             SELECT pr.rate_per_hour FROM parking_rate pr
                             JOIN parking_slot sl ON sl.lot_id = pr.lot_id
                             JOIN vehicle v ON v.vehicle_type = pr.vehicle_type
                             WHERE sl.slot_id = NEW.slot_id AND v.vehicle_id = NEW.vehicle_id), 2),
        session_status = 'Completed'
    WHERE session_id = NEW.session_id;
    UPDATE parking_slot SET status = 'Available' WHERE slot_id = NEW.slot_id;
    UPDATE booking SET booking_status = 'Completed'
    WHERE booking_id = NEW.booking_id AND NEW.booking_id IS NOT NULL;
END;

-- Booking validation
CREATE TRIGGER trg_before_booking_insert
BEFORE INSERT ON booking
BEGIN
    SELECT RAISE(ABORT, 'Cannot book a slot that is under maintenance')
    WHERE (SELECT status FROM parking_slot WHERE slot_id = NEW.slot_id) = 'Maintenance';
    SELECT RAISE(ABORT, 'Slot is already occupied or reserved')
    WHERE (SELECT status FROM parking_slot WHERE slot_id = NEW.slot_id) <> 'Available';
    SELECT RAISE(ABORT, 'Slot type does not match vehicle type')
    WHERE (SELECT slot_type FROM parking_slot WHERE slot_id = NEW.slot_id)
       <> (SELECT vehicle_type FROM vehicle WHERE vehicle_id = NEW.vehicle_id);
END;

CREATE TRIGGER trg_after_booking_insert
AFTER INSERT ON booking
WHEN NEW.booking_status = 'Confirmed'
BEGIN
    UPDATE parking_slot SET status = 'Reserved'
    WHERE slot_id = NEW.slot_id AND status = 'Available';
END;

CREATE TRIGGER trg_after_booking_cancel
AFTER UPDATE OF booking_status ON booking
WHEN NEW.booking_status = 'Cancelled' AND OLD.booking_status = 'Confirmed'
BEGIN
    UPDATE parking_slot SET status = 'Available'
    WHERE slot_id = NEW.slot_id AND status = 'Reserved';
END;
