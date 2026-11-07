-- =====================================================================
-- SMART PARKING MANAGEMENT SYSTEM
-- Views, Triggers, Stored Procedures and Function
-- DBMS: MySQL 8.0.16+
-- =====================================================================
USE smart_parking_system;

-- =====================================================================
-- VIEWS
-- =====================================================================

-- Slot status is CALCULATED here, never stored:
--   under maintenance            -> Maintenance
--   a car is parked in it        -> Occupied
--   a confirmed booking holds it -> Reserved
--   otherwise                    -> Available
-- The UNIQUE keys on active_slot and confirmed_slot guarantee at most one
-- matching session and one matching booking, so each slot appears once.
CREATE OR REPLACE VIEW vw_slot_status AS
SELECT
    sl.slot_id, sl.lot_id, sl.slot_number, sl.floor_number, sl.slot_type,
    sl.under_maintenance,
    CASE
        WHEN sl.under_maintenance      THEN 'Maintenance'
        WHEN s.session_id IS NOT NULL  THEN 'Occupied'
        WHEN b.booking_id IS NOT NULL  THEN 'Reserved'
        ELSE 'Available'
    END                AS status,
    s.session_id       AS active_session_id,
    s.vehicle_id       AS parked_vehicle_id,
    b.booking_id       AS confirmed_booking_id
FROM parking_slot sl
LEFT JOIN parking_session s ON s.active_slot    = sl.slot_id
LEFT JOIN booking b         ON b.confirmed_slot = sl.slot_id;

-- Free / occupied / reserved slots per lot and vehicle type
CREATE OR REPLACE VIEW vw_slot_availability AS
SELECT
    pl.lot_id, pl.lot_name, ss.slot_type,
    COUNT(*)                                                  AS total_slots,
    SUM(CASE WHEN ss.status = 'Available' THEN 1 ELSE 0 END)  AS available_slots,
    SUM(CASE WHEN ss.status = 'Occupied'  THEN 1 ELSE 0 END)  AS occupied_slots,
    SUM(CASE WHEN ss.status = 'Reserved'  THEN 1 ELSE 0 END)  AS reserved_slots
FROM vw_slot_status ss
JOIN parking_lot pl ON pl.lot_id = ss.lot_id
GROUP BY pl.lot_id, pl.lot_name, ss.slot_type;

-- Vehicles parked right now
CREATE OR REPLACE VIEW vw_active_sessions AS
SELECT
    s.session_id, v.vehicle_number, v.vehicle_type,
    c.full_name AS customer_name, pl.lot_name, sl.slot_number, s.entry_time
FROM parking_session s
JOIN vehicle v       ON v.vehicle_id  = s.vehicle_id
JOIN customer c      ON c.customer_id = v.customer_id
JOIN parking_slot sl ON sl.slot_id    = s.slot_id
JOIN parking_lot pl  ON pl.lot_id     = sl.lot_id
WHERE s.exit_time IS NULL;

-- Revenue per lot: the amount comes from the bill (amount_due), stored once
CREATE OR REPLACE VIEW vw_revenue_per_lot AS
SELECT
    pl.lot_id, pl.lot_name,
    COUNT(p.payment_id) AS total_transactions,
    SUM(s.amount_due)   AS total_revenue
FROM payment p
JOIN parking_session s ON s.session_id = p.session_id
JOIN parking_slot sl   ON sl.slot_id   = s.slot_id
JOIN parking_lot pl    ON pl.lot_id    = sl.lot_id
WHERE p.payment_status = 'Paid'
GROUP BY pl.lot_id, pl.lot_name;

-- =====================================================================
-- FUNCTION
-- =====================================================================
DROP FUNCTION IF EXISTS fn_occupancy_percent;
DELIMITER $$
CREATE FUNCTION fn_occupancy_percent (p_lot_id INT)
RETURNS DECIMAL(5,2)
READS SQL DATA
BEGIN
    DECLARE v_total    INT DEFAULT 0;
    DECLARE v_occupied INT DEFAULT 0;
    SELECT COUNT(*) INTO v_total FROM parking_slot WHERE lot_id = p_lot_id;
    SELECT COUNT(*) INTO v_occupied
    FROM parking_session s JOIN parking_slot sl ON sl.slot_id = s.slot_id
    WHERE sl.lot_id = p_lot_id AND s.exit_time IS NULL;
    IF v_total = 0 THEN
        RETURN NULL;
    END IF;
    RETURN ROUND(v_occupied * 100.0 / v_total, 2);
END$$
DELIMITER ;

-- =====================================================================
-- TRIGGERS — each one blocks an anomaly the table structure alone cannot
-- =====================================================================

-- 1. A new booking must be for a free slot of the right type.
DROP TRIGGER IF EXISTS trg_before_booking_insert;
DELIMITER $$
CREATE TRIGGER trg_before_booking_insert
BEFORE INSERT ON booking
FOR EACH ROW
BEGIN
    DECLARE v_maint     BOOLEAN DEFAULT NULL;
    DECLARE v_slot_type VARCHAR(20) DEFAULT NULL;
    DECLARE v_veh_type  VARCHAR(20) DEFAULT NULL;

    SELECT under_maintenance, slot_type INTO v_maint, v_slot_type
    FROM parking_slot WHERE slot_id = NEW.slot_id;
    SELECT vehicle_type INTO v_veh_type FROM vehicle WHERE vehicle_id = NEW.vehicle_id;

    IF NEW.booking_status = 'Confirmed' THEN
        IF v_maint THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Cannot book a slot that is under maintenance';
        END IF;
        IF EXISTS (SELECT 1 FROM parking_session WHERE active_slot = NEW.slot_id)
           OR EXISTS (SELECT 1 FROM booking WHERE confirmed_slot = NEW.slot_id) THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Slot is already occupied or reserved';
        END IF;
        IF v_slot_type <> v_veh_type THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Slot type does not match vehicle type';
        END IF;
    END IF;
END$$
DELIMITER ;

-- 2. A closed booking (Completed / Cancelled) cannot be reopened or changed.
DROP TRIGGER IF EXISTS trg_before_booking_update;
DELIMITER $$
CREATE TRIGGER trg_before_booking_update
BEFORE UPDATE ON booking
FOR EACH ROW
BEGIN
    IF OLD.booking_status <> 'Confirmed' AND NEW.booking_status <> OLD.booking_status THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'A closed booking cannot be reopened';
    END IF;
    IF NEW.vehicle_id <> OLD.vehicle_id OR NEW.slot_id <> OLD.slot_id THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Cancel the booking and make a new one instead';
    END IF;
END$$
DELIMITER ;

-- 3. A car entering must use a free slot of the right type, and a
--    pre-booked car must use exactly the vehicle and slot it booked.
DROP TRIGGER IF EXISTS trg_before_session_insert;
DELIMITER $$
CREATE TRIGGER trg_before_session_insert
BEFORE INSERT ON parking_session
FOR EACH ROW
BEGIN
    DECLARE v_maint     BOOLEAN DEFAULT NULL;
    DECLARE v_slot_type VARCHAR(20) DEFAULT NULL;
    DECLARE v_veh_type  VARCHAR(20) DEFAULT NULL;
    DECLARE v_b_vehicle INT DEFAULT NULL;
    DECLARE v_b_slot    INT DEFAULT NULL;
    DECLARE v_b_status  VARCHAR(20) DEFAULT NULL;

    IF NEW.booking_id IS NOT NULL THEN
        SELECT vehicle_id, slot_id, booking_status INTO v_b_vehicle, v_b_slot, v_b_status
        FROM booking WHERE booking_id = NEW.booking_id;
        IF v_b_vehicle <> NEW.vehicle_id OR v_b_slot <> NEW.slot_id THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Session must use the booked vehicle and slot';
        END IF;
    END IF;

    IF NEW.exit_time IS NULL THEN                 -- a car arriving now
        SELECT under_maintenance, slot_type INTO v_maint, v_slot_type
        FROM parking_slot WHERE slot_id = NEW.slot_id;
        SELECT vehicle_type INTO v_veh_type FROM vehicle WHERE vehicle_id = NEW.vehicle_id;

        IF NEW.booking_id IS NOT NULL AND v_b_status <> 'Confirmed' THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Only confirmed bookings can be checked in';
        END IF;
        IF v_maint THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Slot is under maintenance';
        END IF;
        IF v_slot_type <> v_veh_type THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Slot type does not match vehicle type';
        END IF;
        IF EXISTS (SELECT 1 FROM parking_session WHERE active_vehicle = NEW.vehicle_id) THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'This vehicle is already parked';
        END IF;
        IF EXISTS (SELECT 1 FROM parking_session WHERE active_slot = NEW.slot_id) THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Slot is already occupied';
        END IF;
        IF EXISTS (SELECT 1 FROM booking WHERE confirmed_slot = NEW.slot_id
                   AND booking_id <> IFNULL(NEW.booking_id, 0)) THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Slot is reserved for another booking';
        END IF;
    END IF;
END$$
DELIMITER ;

-- 4. Billing on exit: amount = hours x lot rate for the vehicle type
--    (minimum one hour). A finished session cannot be edited.
DROP TRIGGER IF EXISTS trg_before_session_update;
DELIMITER $$
CREATE TRIGGER trg_before_session_update
BEFORE UPDATE ON parking_session
FOR EACH ROW
BEGIN
    IF NEW.vehicle_id <> OLD.vehicle_id OR NEW.slot_id <> OLD.slot_id
       OR NEW.entry_time <> OLD.entry_time THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Vehicle, slot and entry time cannot be changed';
    END IF;

    IF OLD.exit_time IS NOT NULL THEN
        IF NEW.exit_time IS NULL OR NEW.exit_time <> OLD.exit_time
           OR NOT (NEW.amount_due <=> OLD.amount_due) THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'A completed session cannot be changed';
        END IF;
    ELSEIF NEW.exit_time IS NOT NULL THEN
        SET NEW.amount_due = ROUND(
            GREATEST(ROUND(TIMESTAMPDIFF(MINUTE, NEW.entry_time, NEW.exit_time) / 60, 2), 1.00) * (
                SELECT pr.rate_per_hour
                FROM parking_rate pr
                JOIN parking_slot sl ON sl.lot_id = pr.lot_id
                JOIN vehicle v       ON v.vehicle_type = pr.vehicle_type
                WHERE sl.slot_id = NEW.slot_id AND v.vehicle_id = NEW.vehicle_id
            ), 2);
    END IF;
END$$
DELIMITER ;

-- 5. When a pre-booked stay ends, its booking becomes Completed.
DROP TRIGGER IF EXISTS trg_after_session_update;
DELIMITER $$
CREATE TRIGGER trg_after_session_update
AFTER UPDATE ON parking_session
FOR EACH ROW
BEGIN
    IF OLD.exit_time IS NULL AND NEW.exit_time IS NOT NULL AND NEW.booking_id IS NOT NULL THEN
        UPDATE booking SET booking_status = 'Completed' WHERE booking_id = NEW.booking_id;
    END IF;
END$$
DELIMITER ;

-- 6. Only a finished (billed) stay can be paid.
DROP TRIGGER IF EXISTS trg_before_payment_insert;
DELIMITER $$
CREATE TRIGGER trg_before_payment_insert
BEFORE INSERT ON payment
FOR EACH ROW
BEGIN
    IF NOT EXISTS (SELECT 1 FROM parking_session
                   WHERE session_id = NEW.session_id AND exit_time IS NOT NULL) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Only a completed session can be paid';
    END IF;
END$$
DELIMITER ;

-- =====================================================================
-- STORED PROCEDURES
-- =====================================================================

-- Vehicle entry: allocate the first available slot of the right type.
DROP PROCEDURE IF EXISTS sp_vehicle_entry;
DELIMITER $$
CREATE PROCEDURE sp_vehicle_entry (
    IN p_vehicle_id INT,
    IN p_lot_id     INT
)
BEGIN
    DECLARE v_type    VARCHAR(20) DEFAULT NULL;
    DECLARE v_slot_id INT DEFAULT NULL;

    SELECT vehicle_type INTO v_type FROM vehicle WHERE vehicle_id = p_vehicle_id;
    IF v_type IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Vehicle not found';
    END IF;
    IF EXISTS (SELECT 1 FROM parking_session WHERE active_vehicle = p_vehicle_id) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'This vehicle is already parked';
    END IF;

    SELECT slot_id INTO v_slot_id
    FROM vw_slot_status
    WHERE lot_id = p_lot_id AND slot_type = v_type AND status = 'Available'
    ORDER BY floor_number, slot_number
    LIMIT 1;

    IF v_slot_id IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'No available slot for this vehicle type';
    END IF;

    INSERT INTO parking_session (vehicle_id, slot_id, entry_time)
    VALUES (p_vehicle_id, v_slot_id, NOW());

    SELECT LAST_INSERT_ID() AS session_id, v_slot_id AS slot_id;
END$$
DELIMITER ;

-- Vehicle exit: stamp the exit time; the trigger computes the bill.
DROP PROCEDURE IF EXISTS sp_vehicle_exit;
DELIMITER $$
CREATE PROCEDURE sp_vehicle_exit (
    IN p_session_id INT
)
BEGIN
    DECLARE v_found INT DEFAULT 0;
    DECLARE v_exit  DATETIME DEFAULT NULL;
    SELECT COUNT(*), MAX(exit_time) INTO v_found, v_exit
    FROM parking_session WHERE session_id = p_session_id;
    IF v_found = 0 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Session not found';
    ELSEIF v_exit IS NOT NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Session is already completed';
    END IF;
    UPDATE parking_session SET exit_time = NOW() WHERE session_id = p_session_id;
END$$
DELIMITER ;

-- Check-in for an advance booking: park in the booked slot.
DROP PROCEDURE IF EXISTS sp_booking_checkin;
DELIMITER $$
CREATE PROCEDURE sp_booking_checkin (
    IN p_booking_id INT
)
BEGIN
    DECLARE v_vehicle INT DEFAULT NULL;
    DECLARE v_slot    INT DEFAULT NULL;
    DECLARE v_status  VARCHAR(20) DEFAULT NULL;

    SELECT vehicle_id, slot_id, booking_status INTO v_vehicle, v_slot, v_status
    FROM booking WHERE booking_id = p_booking_id;
    IF v_status IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Booking not found';
    ELSEIF v_status <> 'Confirmed' THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Only confirmed bookings can be checked in';
    END IF;

    INSERT INTO parking_session (booking_id, vehicle_id, slot_id, entry_time)
    VALUES (p_booking_id, v_vehicle, v_slot, NOW());

    SELECT LAST_INSERT_ID() AS session_id, v_slot AS slot_id;
END$$
DELIMITER ;
