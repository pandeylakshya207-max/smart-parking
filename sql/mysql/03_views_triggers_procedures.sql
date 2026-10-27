-- =====================================================================
-- SMART PARKING MANAGEMENT SYSTEM
-- Views, Triggers, Stored Procedures & Functions
-- DBMS: MySQL 8.0+
-- =====================================================================
USE smart_parking_system;

-- ---------------------------------------------------------------------
-- VIEW 1: Real-time slot availability per lot
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW vw_slot_availability AS
SELECT
    pl.lot_id,
    pl.lot_name,
    ps.slot_type,
    COUNT(*)                                              AS total_slots,
    SUM(CASE WHEN ps.status = 'Available' THEN 1 ELSE 0 END) AS available_slots,
    SUM(CASE WHEN ps.status = 'Occupied'  THEN 1 ELSE 0 END) AS occupied_slots
FROM parking_slot ps
JOIN parking_lot pl ON pl.lot_id = ps.lot_id
GROUP BY pl.lot_id, pl.lot_name, ps.slot_type;

-- ---------------------------------------------------------------------
-- VIEW 2: Currently active (vehicles inside the lot right now)
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW vw_active_sessions AS
SELECT
    s.session_id, v.vehicle_number, v.vehicle_type,
    c.full_name AS customer_name, pl.lot_name, sl.slot_number,
    s.entry_time
FROM parking_session s
JOIN vehicle v       ON v.vehicle_id = s.vehicle_id
JOIN customer c      ON c.customer_id = v.customer_id
JOIN parking_slot sl ON sl.slot_id = s.slot_id
JOIN parking_lot pl  ON pl.lot_id = sl.lot_id
WHERE s.session_status = 'Active';

-- ---------------------------------------------------------------------
-- VIEW 3: Revenue summary per parking lot
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW vw_revenue_per_lot AS
SELECT
    pl.lot_id, pl.lot_name,
    COUNT(p.payment_id)      AS total_transactions,
    SUM(p.amount_paid)       AS total_revenue
FROM payment p
JOIN parking_session s ON s.session_id = p.session_id
JOIN parking_slot sl   ON sl.slot_id = s.slot_id
JOIN parking_lot pl    ON pl.lot_id = sl.lot_id
GROUP BY pl.lot_id, pl.lot_name;

-- ---------------------------------------------------------------------
-- TRIGGER 1: When a vehicle enters (new session), mark its slot Occupied
-- ---------------------------------------------------------------------
DELIMITER $$
CREATE TRIGGER trg_after_session_insert
AFTER INSERT ON parking_session
FOR EACH ROW
BEGIN
    UPDATE parking_slot
    SET status = 'Occupied'
    WHERE slot_id = NEW.slot_id;
END$$
DELIMITER ;

-- ---------------------------------------------------------------------
-- TRIGGER 2: When a vehicle exits (exit_time filled in), free the slot
-- and auto-calculate billing amount based on the lot's hourly rate
-- ---------------------------------------------------------------------
DELIMITER $$
CREATE TRIGGER trg_before_session_update
BEFORE UPDATE ON parking_session
FOR EACH ROW
BEGIN
    IF NEW.exit_time IS NOT NULL AND OLD.exit_time IS NULL THEN
        SET NEW.total_hours = ROUND(TIMESTAMPDIFF(MINUTE, NEW.entry_time, NEW.exit_time) / 60.0, 2);
        SET NEW.session_status = 'Completed';
        SET NEW.amount_due = NEW.total_hours * (
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

DELIMITER $$
CREATE TRIGGER trg_after_session_exit
AFTER UPDATE ON parking_session
FOR EACH ROW
BEGIN
    IF NEW.session_status = 'Completed' AND OLD.session_status = 'Active' THEN
        UPDATE parking_slot SET status = 'Available' WHERE slot_id = NEW.slot_id;
    END IF;
END$$
DELIMITER ;

-- ---------------------------------------------------------------------
-- TRIGGER 3: Prevent booking a slot that is already Occupied/Maintenance
-- ---------------------------------------------------------------------
DELIMITER $$
CREATE TRIGGER trg_before_booking_insert
BEFORE INSERT ON booking
FOR EACH ROW
BEGIN
    DECLARE slot_status VARCHAR(20);
    SELECT status INTO slot_status FROM parking_slot WHERE slot_id = NEW.slot_id;
    IF slot_status = 'Maintenance' THEN
        SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'Cannot book a slot that is under maintenance';
    END IF;
END$$
DELIMITER ;

-- ---------------------------------------------------------------------
-- STORED PROCEDURE 1: Vehicle Entry — allocate the first available slot
-- of the right type and open a new parking session
-- ---------------------------------------------------------------------
DELIMITER $$
CREATE PROCEDURE sp_vehicle_entry (
    IN p_vehicle_id INT,
    IN p_lot_id     INT
)
BEGIN
    DECLARE v_slot_id INT;
    DECLARE v_type VARCHAR(20);

    SELECT vehicle_type INTO v_type FROM vehicle WHERE vehicle_id = p_vehicle_id;

    SELECT slot_id INTO v_slot_id
    FROM parking_slot
    WHERE lot_id = p_lot_id AND slot_type = v_type AND status = 'Available'
    LIMIT 1;

    IF v_slot_id IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'No available slot for this vehicle type';
    ELSE
        INSERT INTO parking_session (vehicle_id, slot_id, entry_time, session_status)
        VALUES (p_vehicle_id, v_slot_id, NOW(), 'Active');
    END IF;
END$$
DELIMITER ;

-- ---------------------------------------------------------------------
-- STORED PROCEDURE 2: Vehicle Exit — close session, bill, free slot
-- (billing math itself is handled by trg_before_session_update)
-- ---------------------------------------------------------------------
DELIMITER $$
CREATE PROCEDURE sp_vehicle_exit (
    IN p_session_id INT
)
BEGIN
    UPDATE parking_session
    SET exit_time = NOW()
    WHERE session_id = p_session_id;
END$$
DELIMITER ;

-- ---------------------------------------------------------------------
-- FUNCTION: Return current occupancy percentage of a given lot
-- ---------------------------------------------------------------------
DELIMITER $$
CREATE FUNCTION fn_occupancy_percent (p_lot_id INT)
RETURNS DECIMAL(5,2)
DETERMINISTIC
BEGIN
    DECLARE total INT;
    DECLARE occupied INT;
    SELECT COUNT(*) INTO total FROM parking_slot WHERE lot_id = p_lot_id;
    SELECT COUNT(*) INTO occupied FROM parking_slot WHERE lot_id = p_lot_id AND status = 'Occupied';
    RETURN ROUND((occupied / total) * 100, 2);
END$$
DELIMITER ;
