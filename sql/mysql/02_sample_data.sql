-- =====================================================================
-- SMART PARKING MANAGEMENT SYSTEM
-- Sample Data (DML)
-- Every fact is entered once. Slot status, hours and session status are
-- NOT entered — the database calculates them.
-- =====================================================================
USE smart_parking_system;

-- 1. Parking lots
INSERT INTO parking_lot (lot_name, location, total_floors, contact_number) VALUES
('Central Mall Parking',    'MG Road, Bengaluru',    3, '9845012345'),
('Tech Park Parking',       'Whitefield, Bengaluru', 2, '9845098765'),
('Railway Station Parking', 'City Railway Station',  1, '9845011122');

-- 2. Customers
INSERT INTO customer (full_name, email, phone, password_hash, registered_on) VALUES
('Rohan Sharma',   'rohan.sharma@mail.com', '9900011111', 'hash_pw_1', '2025-01-10'),
('Ananya Iyer',    'ananya.iyer@mail.com',  '9900022222', 'hash_pw_2', '2025-01-15'),
('Vikram Rao',     'vikram.rao@mail.com',   '9900033333', 'hash_pw_3', '2025-02-02'),
('Sneha Kulkarni', 'sneha.k@mail.com',      '9900044444', 'hash_pw_4', '2025-02-20'),
('Arjun Mehta',    'arjun.mehta@mail.com',  '9900055555', 'hash_pw_5', '2025-03-05'),
('Priya Nair',     'priya.nair@mail.com',   '9900066666', 'hash_pw_6', '2025-03-18'),
('Karan Verma',    'karan.verma@mail.com',  '9900077777', 'hash_pw_7', '2025-04-01'),
('Divya Reddy',    'divya.reddy@mail.com',  '9900088888', 'hash_pw_8', '2025-04-12');

-- 3. Staff
INSERT INTO staff (lot_id, full_name, designation, shift, phone) VALUES
(1, 'Suresh Kumar', 'Manager',   'Morning', '9880011111'),
(1, 'Manoj Pillai', 'Attendant', 'Evening', '9880022222'),
(2, 'Ravi Teja',    'Manager',   'Morning', '9880033333'),
(2, 'Ganesh Naik',  'Security',  'Night',   '9880044444'),
(3, 'Lakshmi Devi', 'Attendant', 'Morning', '9880055555');

-- 4. Parking slots — only the maintenance flag is stored
INSERT INTO parking_slot (lot_id, slot_number, floor_number, slot_type, under_maintenance) VALUES
(1,'A1',1,'Car',FALSE),(1,'A2',1,'Car',FALSE),(1,'A3',1,'Car',FALSE),
(1,'A4',1,'Handicap',FALSE),(1,'B1',2,'Bike',FALSE),(1,'B2',2,'Bike',FALSE),
(1,'B3',2,'EV',FALSE),(1,'C1',3,'Car',TRUE),
(2,'T1',1,'Car',FALSE),(2,'T2',1,'Car',FALSE),(2,'T3',1,'EV',FALSE),
(2,'T4',2,'Bike',FALSE),(2,'T5',2,'Car',FALSE),
(3,'R1',1,'Car',FALSE),(3,'R2',1,'Bike',FALSE),(3,'R3',1,'Car',FALSE),
(3,'R4',1,'Handicap',FALSE);

-- 5. Vehicles
INSERT INTO vehicle (customer_id, vehicle_number, vehicle_type, model_name) VALUES
(1, 'KA01AB1234', 'Car',      'Hyundai Creta'),
(2, 'KA02CD5678', 'Bike',     'Royal Enfield Classic'),
(3, 'KA03EF9012', 'Car',      'Maruti Swift'),
(4, 'KA04GH3456', 'EV',       'Tata Nexon EV'),
(5, 'KA05IJ7890', 'Car',      'Honda City'),
(6, 'KA06KL2345', 'Bike',     'TVS Jupiter'),
(7, 'KA07MN6789', 'Car',      'Toyota Innova'),
(8, 'KA08OP0123', 'Handicap', 'Maruti Wagon R (Modified)');

-- 6. Rate card (per lot, per vehicle type)
INSERT INTO parking_rate (lot_id, vehicle_type, rate_per_hour) VALUES
(1,'Car',40.00),(1,'Bike',15.00),(1,'EV',30.00),(1,'Handicap',20.00),
(2,'Car',35.00),(2,'Bike',10.00),(2,'EV',25.00),(2,'Handicap',15.00),
(3,'Car',30.00),(3,'Bike',10.00),(3,'EV',25.00),(3,'Handicap',15.00);

-- 7. Bookings — the customer is found through the vehicle
INSERT INTO booking (vehicle_id, slot_id, start_time, end_time, booking_status) VALUES
(1, 2,  '2026-08-20 09:00:00', '2026-08-20 13:00:00', 'Completed'),
(4, 7,  '2026-12-05 10:00:00', '2026-12-05 18:00:00', 'Confirmed'),
(7, 9,  '2026-08-22 08:30:00', '2026-08-22 20:00:00', 'Completed'),
(2, 6,  '2026-08-23 11:00:00', '2026-08-23 15:00:00', 'Cancelled');

-- 8. Parking sessions — hours and status are calculated, the amount
--    is the price that was charged at the time
INSERT INTO parking_session (booking_id, vehicle_id, slot_id, entry_time, exit_time, amount_due) VALUES
(1,    1, 2,  '2026-08-20 09:05:00', '2026-08-20 13:10:00', 163.20),
(3,    7, 9,  '2026-08-22 08:35:00', '2026-08-22 19:50:00', 393.75),
(NULL, 3, 14, '2026-08-24 09:00:00', '2026-08-24 12:30:00', 105.00),
(NULL, 5, 9,  '2026-08-24 14:00:00', NULL, NULL),
(NULL, 6, 15, '2026-08-24 15:30:00', NULL, NULL),
(NULL, 2, 6,  '2026-08-25 08:00:00', '2026-08-25 09:45:00', 26.25);

-- 9. Payments — the amount is the session's amount_due
INSERT INTO payment (session_id, payment_mode, payment_date, payment_status) VALUES
(1, 'UPI',    '2026-08-20 13:12:00', 'Paid'),
(2, 'Card',   '2026-08-22 19:52:00', 'Paid'),
(3, 'Cash',   '2026-08-24 12:32:00', 'Paid'),
(6, 'Wallet', '2026-08-25 09:47:00', 'Paid');
