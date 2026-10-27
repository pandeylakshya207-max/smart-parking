-- =====================================================================
-- SMART PARKING MANAGEMENT SYSTEM
-- Application extensions (run AFTER 03_views_triggers_procedures.sql)
-- Adds the database logic the web app needs for the full booking
-- lifecycle and closes gaps found while building the working model.
-- DBMS: MySQL 8.0+ / MariaDB 10.4+
-- =====================================================================
USE smart_parking_system;

-- ---------------------------------------------------------------------
-- TRIGGER (replaces report version): validate a new booking.
-- Blocks Maintenance (as in the report) and also Occupied/Reserved slots,
-- and a vehicle whose type does not match the slot type.
-- ---------------------------------------------------------------------
DROP TRIGGER IF EXISTS trg_before_booking_insert;
DELIMITER $$
CREATE TRIGGER trg_before_booking_insert
BEFORE INSERT ON booking
FOR EACH ROW
BEGIN
    DECLARE v_slot_status VARCHAR(20);
    DECLARE v_slot_type   VARCHAR(20);
    DECLARE v_veh_type    VARCHAR(20);

    SELECT status, slot_type INTO v_slot_status, v_slot_type
    FROM parking_slot WHERE slot_id = NEW.slot_id;

    SELECT vehicle_type INTO v_veh_type
    FROM vehicle WHERE vehicle_id = NEW.vehicle_id;

    IF v_slot_status = 'Maintenance' THEN
        SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'Cannot book a slot that is under maintenance';
    ELSEIF v_slot_status <> 'Available' THEN
        SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'Slot is already occupied or reserved';
    ELSEIF v_slot_type <> v_veh_type THEN
        SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'Slot type does not match vehicle type';
    END IF;
END$$
DELIMITER ;

-- ---------------------------------------------------------------------
-- TRIGGER: a confirmed booking reserves its slot
-- ---------------------------------------------------------------------
DROP TRIGGER IF EXISTS trg_after_booking_insert;
DELIMITER $$
CREATE TRIGGER trg_after_booking_insert
AFTER INSERT ON booking
FOR EACH ROW
BEGIN
    IF NEW.booking_status = 'Confirmed' THEN
        UPDATE parking_slot SET status = 'Reserved'
        WHERE slot_id = NEW.slot_id AND status = 'Available';
    END IF;
END$$
DELIMITER ;

-- ---------------------------------------------------------------------
-- TRIGGER: cancelling a booking releases a reserved slot
-- ---------------------------------------------------------------------
DROP TRIGGER IF EXISTS trg_after_booking_cancel;
DELIMITER $$
CREATE TRIGGER trg_after_booking_cancel
AFTER UPDATE ON booking
FOR EACH ROW
BEGIN
    IF NEW.booking_status = 'Cancelled' AND OLD.booking_status = 'Confirmed' THEN
        UPDATE parking_slot SET status = 'Available'
        WHERE slot_id = NEW.slot_id AND status = 'Reserved';
    END IF;
END$$
DELIMITER ;

-- ---------------------------------------------------------------------
-- TRIGGER: when a pre-booked session completes, mark its booking Completed
-- (runs alongside the report's trg_after_session_exit)
-- ---------------------------------------------------------------------
DROP TRIGGER IF EXISTS trg_after_session_complete_booking;
DELIMITER $$
CREATE TRIGGER trg_after_session_complete_booking
AFTER UPDATE ON parking_session
FOR EACH ROW
BEGIN
    IF NEW.session_status = 'Completed' AND OLD.session_status = 'Active'
       AND NEW.booking_id IS NOT NULL THEN
        UPDATE booking SET booking_status = 'Completed'
        WHERE booking_id = NEW.booking_id;
    END IF;
END$$
DELIMITER ;

-- ---------------------------------------------------------------------
-- PROCEDURE (replaces report version): vehicle entry for walk-ins.
-- Same allocation rule as the report, plus two guards:
--   * the vehicle must exist
--   * the vehicle must not already be parked somewhere
-- Returns the new session_id and the allocated slot.
-- ---------------------------------------------------------------------
DROP PROCEDURE IF EXISTS sp_vehicle_entry;
DELIMITER $$
CREATE PROCEDURE sp_vehicle_entry (
    IN p_vehicle_id INT,
    IN p_lot_id     INT
)
BEGIN
    DECLARE v_slot_id INT DEFAULT NULL;
    DECLARE v_type    VARCHAR(20) DEFAULT NULL;
    DECLARE v_active  INT DEFAULT 0;

    SELECT vehicle_type INTO v_type FROM vehicle WHERE vehicle_id = p_vehicle_id;
    IF v_type IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Vehicle not found';
    END IF;

    SELECT COUNT(*) INTO v_active FROM parking_session
    WHERE vehicle_id = p_vehicle_id AND session_status = 'Active';
    IF v_active > 0 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'This vehicle is already parked';
    END IF;

    SELECT slot_id INTO v_slot_id
    FROM parking_slot
    WHERE lot_id = p_lot_id AND slot_type = v_type AND status = 'Available'
    ORDER BY floor_number, slot_number
    LIMIT 1;

    IF v_slot_id IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'No available slot for this vehicle type';
    END IF;

    INSERT INTO parking_session (vehicle_id, slot_id, entry_time, session_status)
    VALUES (p_vehicle_id, v_slot_id, NOW(), 'Active');

    SELECT LAST_INSERT_ID() AS session_id, v_slot_id AS slot_id;
END$$
DELIMITER ;

-- ---------------------------------------------------------------------
-- PROCEDURE (replaces report version): vehicle exit.
-- Refuses to close a session that is not Active; billing is still done
-- by trg_before_session_update exactly as in the report.
-- ---------------------------------------------------------------------
DROP PROCEDURE IF EXISTS sp_vehicle_exit;
DELIMITER $$
CREATE PROCEDURE sp_vehicle_exit (
    IN p_session_id INT
)
BEGIN
    DECLARE v_status VARCHAR(20) DEFAULT NULL;
    SELECT session_status INTO v_status FROM parking_session WHERE session_id = p_session_id;
    IF v_status IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Session not found';
    ELSEIF v_status <> 'Active' THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Session is already completed';
    END IF;

    UPDATE parking_session SET exit_time = NOW() WHERE session_id = p_session_id;
END$$
DELIMITER ;

-- ---------------------------------------------------------------------
-- PROCEDURE: check in a vehicle against its advance booking
-- ---------------------------------------------------------------------
DROP PROCEDURE IF EXISTS sp_booking_checkin;
DELIMITER $$
CREATE PROCEDURE sp_booking_checkin (
    IN p_booking_id INT
)
BEGIN
    DECLARE v_status   VARCHAR(20) DEFAULT NULL;
    DECLARE v_vehicle  INT;
    DECLARE v_slot     INT;
    DECLARE v_slot_st  VARCHAR(20);
    DECLARE v_active   INT DEFAULT 0;

    SELECT booking_status, vehicle_id, slot_id INTO v_status, v_vehicle, v_slot
    FROM booking WHERE booking_id = p_booking_id;

    IF v_status IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Booking not found';
    ELSEIF v_status <> 'Confirmed' THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Only confirmed bookings can be checked in';
    END IF;

    SELECT COUNT(*) INTO v_active FROM parking_session
    WHERE vehicle_id = v_vehicle AND session_status = 'Active';
    IF v_active > 0 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'This vehicle is already parked';
    END IF;

    SELECT status INTO v_slot_st FROM parking_slot WHERE slot_id = v_slot;
    IF v_slot_st IN ('Occupied', 'Maintenance') THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Booked slot is not free right now';
    END IF;

    INSERT INTO parking_session (booking_id, vehicle_id, slot_id, entry_time, session_status)
    VALUES (p_booking_id, v_vehicle, v_slot, NOW(), 'Active');

    SELECT LAST_INSERT_ID() AS session_id, v_slot AS slot_id;
END$$
DELIMITER ;

-- ---------------------------------------------------------------------
-- TRIGGER (replaces report version): billing on exit.
-- Same formula as the report (hours x lot rate for the vehicle type),
-- with a minimum charge of 1 hour so an immediate exit is not billed 0.
-- total_hours still stores the real duration.
-- ---------------------------------------------------------------------
DROP TRIGGER IF EXISTS trg_before_session_update;
DELIMITER $$
CREATE TRIGGER trg_before_session_update
BEFORE UPDATE ON parking_session
FOR EACH ROW
BEGIN
    IF NEW.exit_time IS NOT NULL AND OLD.exit_time IS NULL THEN
        SET NEW.total_hours = ROUND(TIMESTAMPDIFF(MINUTE, NEW.entry_time, NEW.exit_time) / 60.0, 2);
        SET NEW.session_status = 'Completed';
        SET NEW.amount_due = GREATEST(NEW.total_hours, 1.00) * (
            SELECT pr.rate_per_hour
            FROM parking_rate pr
            JOIN parking_slot sl ON sl.lot_id = pr.lot_id
            JOIN vehicle v ON v.vehicle_type = pr.vehicle_type
            WHERE sl.slot_id = NEW.slot_id AND v.vehicle_id = NEW.vehicle_id
            LIMIT 1
        );
    END IF;
END$$
DELIMITER ;
