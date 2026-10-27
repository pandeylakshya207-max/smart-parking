-- =====================================================================
-- SMART PARKING MANAGEMENT SYSTEM
-- Database Schema (DDL)
-- DBMS: MySQL 8.0+
-- =====================================================================

DROP DATABASE IF EXISTS smart_parking_system;
CREATE DATABASE smart_parking_system;
USE smart_parking_system;

-- ---------------------------------------------------------------------
-- 1. PARKING_LOT  — a physical parking facility/branch
-- ---------------------------------------------------------------------
CREATE TABLE parking_lot (
    lot_id          INT AUTO_INCREMENT PRIMARY KEY,
    lot_name        VARCHAR(60)  NOT NULL,
    location        VARCHAR(120) NOT NULL,
    total_floors    INT NOT NULL DEFAULT 1,
    total_slots     INT NOT NULL,
    contact_number  VARCHAR(15) NOT NULL,
    CONSTRAINT chk_total_slots CHECK (total_slots > 0)
);

-- ---------------------------------------------------------------------
-- 2. CUSTOMER — registered users of the system
-- ---------------------------------------------------------------------
CREATE TABLE customer (
    customer_id     INT AUTO_INCREMENT PRIMARY KEY,
    full_name       VARCHAR(60) NOT NULL,
    email           VARCHAR(80) UNIQUE NOT NULL,
    phone           VARCHAR(15) UNIQUE NOT NULL,
    password_hash   VARCHAR(120) NOT NULL,
    registered_on   DATE NOT NULL DEFAULT (CURRENT_DATE)
);

-- ---------------------------------------------------------------------
-- 3. STAFF — employees who manage a parking lot
-- ---------------------------------------------------------------------
CREATE TABLE staff (
    staff_id        INT AUTO_INCREMENT PRIMARY KEY,
    lot_id          INT NOT NULL,
    full_name       VARCHAR(60) NOT NULL,
    designation     VARCHAR(30) NOT NULL,           -- e.g. Manager, Attendant, Security
    shift           ENUM('Morning','Evening','Night') NOT NULL,
    phone           VARCHAR(15) NOT NULL,
    FOREIGN KEY (lot_id) REFERENCES parking_lot(lot_id)
        ON DELETE CASCADE ON UPDATE CASCADE
);

-- ---------------------------------------------------------------------
-- 4. PARKING_SLOT — individual parking spaces inside a lot
-- ---------------------------------------------------------------------
CREATE TABLE parking_slot (
    slot_id         INT AUTO_INCREMENT PRIMARY KEY,
    lot_id          INT NOT NULL,
    slot_number     VARCHAR(10) NOT NULL,
    floor_number    INT NOT NULL DEFAULT 1,
    slot_type       ENUM('Car','Bike','EV','Handicap') NOT NULL DEFAULT 'Car',
    status          ENUM('Available','Occupied','Reserved','Maintenance') NOT NULL DEFAULT 'Available',
    FOREIGN KEY (lot_id) REFERENCES parking_lot(lot_id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    UNIQUE KEY uq_slot_per_lot (lot_id, slot_number)
);

-- ---------------------------------------------------------------------
-- 5. VEHICLE — vehicles owned by customers
-- ---------------------------------------------------------------------
CREATE TABLE vehicle (
    vehicle_id      INT AUTO_INCREMENT PRIMARY KEY,
    customer_id     INT NOT NULL,
    vehicle_number  VARCHAR(15) UNIQUE NOT NULL,
    vehicle_type    ENUM('Car','Bike','EV','Handicap') NOT NULL,
    model_name      VARCHAR(40),
    FOREIGN KEY (customer_id) REFERENCES customer(customer_id)
        ON DELETE CASCADE ON UPDATE CASCADE
);

-- ---------------------------------------------------------------------
-- 6. PARKING_RATE — hourly rate charged per vehicle type, per lot
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
-- 7. BOOKING — advance reservation of a slot made by a customer
-- ---------------------------------------------------------------------
CREATE TABLE booking (
    booking_id      INT AUTO_INCREMENT PRIMARY KEY,
    customer_id     INT NOT NULL,
    vehicle_id      INT NOT NULL,
    slot_id         INT NOT NULL,
    booking_date    DATE NOT NULL,
    start_time      DATETIME NOT NULL,
    end_time        DATETIME NOT NULL,
    booking_status  ENUM('Confirmed','Cancelled','Completed') NOT NULL DEFAULT 'Confirmed',
    FOREIGN KEY (customer_id) REFERENCES customer(customer_id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    FOREIGN KEY (vehicle_id) REFERENCES vehicle(vehicle_id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    FOREIGN KEY (slot_id) REFERENCES parking_slot(slot_id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT chk_booking_time CHECK (end_time > start_time)
);

-- ---------------------------------------------------------------------
-- 8. PARKING_SESSION — actual entry/exit record of a vehicle
-- ---------------------------------------------------------------------
CREATE TABLE parking_session (
    session_id      INT AUTO_INCREMENT PRIMARY KEY,
    booking_id      INT NULL,                       -- NULL if walk-in (no pre-booking)
    vehicle_id      INT NOT NULL,
    slot_id         INT NOT NULL,
    entry_time      DATETIME NOT NULL,
    exit_time       DATETIME NULL,
    total_hours     DECIMAL(5,2) NULL,
    amount_due      DECIMAL(8,2) NULL,
    session_status  ENUM('Active','Completed') NOT NULL DEFAULT 'Active',
    FOREIGN KEY (booking_id) REFERENCES booking(booking_id)
        ON DELETE SET NULL ON UPDATE CASCADE,
    FOREIGN KEY (vehicle_id) REFERENCES vehicle(vehicle_id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    FOREIGN KEY (slot_id) REFERENCES parking_slot(slot_id)
        ON DELETE CASCADE ON UPDATE CASCADE
);

-- ---------------------------------------------------------------------
-- 9. PAYMENT — payment made for a completed parking session
-- ---------------------------------------------------------------------
CREATE TABLE payment (
    payment_id      INT AUTO_INCREMENT PRIMARY KEY,
    session_id      INT NOT NULL UNIQUE,
    amount_paid     DECIMAL(8,2) NOT NULL,
    payment_mode    ENUM('Cash','Card','UPI','Wallet') NOT NULL,
    payment_date    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    payment_status  ENUM('Paid','Pending','Refunded') NOT NULL DEFAULT 'Paid',
    FOREIGN KEY (session_id) REFERENCES parking_session(session_id)
        ON DELETE CASCADE ON UPDATE CASCADE
);

-- ---------------------------------------------------------------------
-- Indexes for frequently queried columns
-- ---------------------------------------------------------------------
CREATE INDEX idx_slot_status        ON parking_slot(status);
CREATE INDEX idx_session_status     ON parking_session(session_status);
CREATE INDEX idx_vehicle_number     ON vehicle(vehicle_number);
CREATE INDEX idx_booking_date       ON booking(booking_date);
