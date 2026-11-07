-- =====================================================================
-- SMART PARKING MANAGEMENT SYSTEM
-- Database Schema (DDL) — normalised, redundancy-free version
-- DBMS: MySQL 8.0.16+ (CHECK constraints, generated columns)
--
-- Design rules applied (see report, Section 3.4):
--   * Store every fact ONCE. Anything that can be calculated from other
--     columns is calculated (view or generated column), never typed in.
--   * Generated columns are computed by MySQL itself, so they can never
--     disagree with the columns they come from.
--   * History (sessions, payments) can never be deleted by accident:
--     those foreign keys use ON DELETE RESTRICT.
--   * MySQL forbids ON UPDATE CASCADE on a column that a stored generated
--     column is built from, so those keys use ON UPDATE RESTRICT
--     (surrogate ids never change, so nothing is lost).
-- =====================================================================

DROP DATABASE IF EXISTS smart_parking_system;
CREATE DATABASE smart_parking_system;
USE smart_parking_system;

-- ---------------------------------------------------------------------
-- 1. PARKING_LOT — a parking facility.
--    (total_slots removed: the number of slots is COUNT(parking_slot).)
-- ---------------------------------------------------------------------
CREATE TABLE parking_lot (
    lot_id          INT AUTO_INCREMENT PRIMARY KEY,
    lot_name        VARCHAR(60)  NOT NULL UNIQUE,
    location        VARCHAR(120) NOT NULL,
    total_floors    INT NOT NULL DEFAULT 1,
    contact_number  VARCHAR(15)  NOT NULL,
    CONSTRAINT chk_floors CHECK (total_floors > 0)
);

-- ---------------------------------------------------------------------
-- 2. CUSTOMER — a registered driver.
-- ---------------------------------------------------------------------
CREATE TABLE customer (
    customer_id     INT AUTO_INCREMENT PRIMARY KEY,
    full_name       VARCHAR(60)  NOT NULL,
    email           VARCHAR(80)  NOT NULL UNIQUE,
    phone           VARCHAR(15)  NOT NULL UNIQUE,
    password_hash   VARCHAR(255) NOT NULL,
    registered_on   DATE NOT NULL DEFAULT (CURRENT_DATE)
);

-- ---------------------------------------------------------------------
-- 3. STAFF — an employee of one lot.
--    designation is an ENUM so the role used for login can't be misspelt.
-- ---------------------------------------------------------------------
CREATE TABLE staff (
    staff_id        INT AUTO_INCREMENT PRIMARY KEY,
    lot_id          INT NOT NULL,
    full_name       VARCHAR(60) NOT NULL,
    designation     ENUM('Manager','Attendant','Security') NOT NULL,
    shift           ENUM('Morning','Evening','Night') NOT NULL,
    phone           VARCHAR(15) NOT NULL UNIQUE,
    FOREIGN KEY (lot_id) REFERENCES parking_lot(lot_id)
        ON DELETE CASCADE ON UPDATE CASCADE
);

-- ---------------------------------------------------------------------
-- 4. PARKING_SLOT — one parking space.
--    (status removed: Occupied / Reserved / Available are calculated by
--     the view vw_slot_status from sessions and bookings. Only the one
--     fact that cannot be calculated — "under maintenance" — is stored.)
-- ---------------------------------------------------------------------
CREATE TABLE parking_slot (
    slot_id           INT AUTO_INCREMENT PRIMARY KEY,
    lot_id            INT NOT NULL,
    slot_number       VARCHAR(10) NOT NULL,
    floor_number      INT NOT NULL DEFAULT 1,
    slot_type         ENUM('Car','Bike','EV','Handicap') NOT NULL DEFAULT 'Car',
    under_maintenance BOOLEAN NOT NULL DEFAULT FALSE,
    FOREIGN KEY (lot_id) REFERENCES parking_lot(lot_id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    UNIQUE KEY uq_slot_per_lot (lot_id, slot_number),
    CONSTRAINT chk_floor CHECK (floor_number > 0)
);

-- ---------------------------------------------------------------------
-- 5. VEHICLE — owned by one customer.
--    RESTRICT: a customer with vehicles cannot be deleted by accident.
-- ---------------------------------------------------------------------
CREATE TABLE vehicle (
    vehicle_id      INT AUTO_INCREMENT PRIMARY KEY,
    customer_id     INT NOT NULL,
    vehicle_number  VARCHAR(15) NOT NULL UNIQUE,
    vehicle_type    ENUM('Car','Bike','EV','Handicap') NOT NULL,
    model_name      VARCHAR(40),
    FOREIGN KEY (customer_id) REFERENCES customer(customer_id)
        ON DELETE RESTRICT ON UPDATE CASCADE
);

-- ---------------------------------------------------------------------
-- 6. PARKING_RATE — hourly price per lot and vehicle type.
-- ---------------------------------------------------------------------
CREATE TABLE parking_rate (
    rate_id         INT AUTO_INCREMENT PRIMARY KEY,
    lot_id          INT NOT NULL,
    vehicle_type    ENUM('Car','Bike','EV','Handicap') NOT NULL,
    rate_per_hour   DECIMAL(6,2) NOT NULL,
    FOREIGN KEY (lot_id) REFERENCES parking_lot(lot_id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    UNIQUE KEY uq_rate_per_type (lot_id, vehicle_type),
    CONSTRAINT chk_rate CHECK (rate_per_hour > 0)
);

-- ---------------------------------------------------------------------
-- 7. BOOKING — an advance reservation of one slot for one vehicle.
--    (customer_id removed: the customer is the vehicle's owner.
--     booking_date removed: it is DATE(start_time).)
--    confirmed_slot is NULL unless the booking is Confirmed, and it is
--    UNIQUE — so a slot can have at most ONE confirmed booking.
-- ---------------------------------------------------------------------
CREATE TABLE booking (
    booking_id      INT AUTO_INCREMENT PRIMARY KEY,
    vehicle_id      INT NOT NULL,
    slot_id         INT NOT NULL,
    start_time      DATETIME NOT NULL,
    end_time        DATETIME NOT NULL,
    booking_status  ENUM('Confirmed','Cancelled','Completed') NOT NULL DEFAULT 'Confirmed',
    confirmed_slot  INT GENERATED ALWAYS AS
                        (IF(booking_status = 'Confirmed', slot_id, NULL)) STORED,
    FOREIGN KEY (vehicle_id) REFERENCES vehicle(vehicle_id)
        ON DELETE RESTRICT ON UPDATE RESTRICT,
    FOREIGN KEY (slot_id) REFERENCES parking_slot(slot_id)
        ON DELETE RESTRICT ON UPDATE RESTRICT,
    UNIQUE KEY uq_one_confirmed_booking_per_slot (confirmed_slot),
    CONSTRAINT chk_booking_time CHECK (end_time > start_time)
);

-- ---------------------------------------------------------------------
-- 8. PARKING_SESSION — one actual stay (entry → exit).
--    session_status and total_hours are GENERATED from entry/exit time,
--    so they can never contradict them.
--    amount_due is stored on purpose: it records the price charged at
--    the time, which must not change if the rate card changes later.
--    active_slot / active_vehicle are NULL once the car has left, and
--    UNIQUE — so a slot can hold only ONE car and a car can be parked
--    in only ONE place at a time.
-- ---------------------------------------------------------------------
CREATE TABLE parking_session (
    session_id      INT AUTO_INCREMENT PRIMARY KEY,
    booking_id      INT NULL,                       -- NULL for walk-ins
    vehicle_id      INT NOT NULL,
    slot_id         INT NOT NULL,
    entry_time      DATETIME NOT NULL,
    exit_time       DATETIME NULL,
    amount_due      DECIMAL(8,2) NULL,
    session_status  VARCHAR(10) GENERATED ALWAYS AS
                        (IF(exit_time IS NULL, 'Active', 'Completed')) STORED,
    total_hours     DECIMAL(6,2) GENERATED ALWAYS AS
                        (ROUND(TIMESTAMPDIFF(MINUTE, entry_time, exit_time) / 60, 2)) STORED,
    active_slot     INT GENERATED ALWAYS AS (IF(exit_time IS NULL, slot_id, NULL)) STORED,
    active_vehicle  INT GENERATED ALWAYS AS (IF(exit_time IS NULL, vehicle_id, NULL)) STORED,
    FOREIGN KEY (booking_id) REFERENCES booking(booking_id)
        ON DELETE SET NULL ON UPDATE CASCADE,
    FOREIGN KEY (vehicle_id) REFERENCES vehicle(vehicle_id)
        ON DELETE RESTRICT ON UPDATE RESTRICT,
    FOREIGN KEY (slot_id) REFERENCES parking_slot(slot_id)
        ON DELETE RESTRICT ON UPDATE RESTRICT,
    UNIQUE KEY uq_one_car_per_slot (active_slot),
    UNIQUE KEY uq_one_slot_per_car (active_vehicle),
    UNIQUE KEY uq_one_session_per_booking (booking_id),
    CONSTRAINT chk_exit_after_entry CHECK (exit_time IS NULL OR exit_time >= entry_time),
    CONSTRAINT chk_amount CHECK (amount_due IS NULL OR amount_due >= 0)
);

-- ---------------------------------------------------------------------
-- 9. PAYMENT — settles one completed session.
--    (amount_paid removed: the amount is the session's amount_due.)
--    RESTRICT: a session that has been paid cannot be deleted.
-- ---------------------------------------------------------------------
CREATE TABLE payment (
    payment_id      INT AUTO_INCREMENT PRIMARY KEY,
    session_id      INT NOT NULL UNIQUE,
    payment_mode    ENUM('Cash','Card','UPI','Wallet') NOT NULL,
    payment_date    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    payment_status  ENUM('Paid','Pending','Refunded') NOT NULL DEFAULT 'Paid',
    FOREIGN KEY (session_id) REFERENCES parking_session(session_id)
        ON DELETE RESTRICT ON UPDATE CASCADE
);

-- ---------------------------------------------------------------------
-- 10. STAFF_ACCOUNT — login for one staff member (1 : 1 with STAFF).
-- ---------------------------------------------------------------------
CREATE TABLE staff_account (
    staff_id        INT PRIMARY KEY,
    username        VARCHAR(40)  NOT NULL UNIQUE,
    password_hash   VARCHAR(255) NOT NULL,
    is_active       BOOLEAN      NOT NULL DEFAULT TRUE,
    last_login      DATETIME     NULL,
    FOREIGN KEY (staff_id) REFERENCES staff(staff_id)
        ON DELETE CASCADE ON UPDATE CASCADE
);

-- ---------------------------------------------------------------------
-- Indexes on columns used in searches and joins
-- ---------------------------------------------------------------------
CREATE INDEX idx_session_entry   ON parking_session(entry_time);
CREATE INDEX idx_booking_start   ON booking(start_time);
CREATE INDEX idx_payment_date    ON payment(payment_date);
