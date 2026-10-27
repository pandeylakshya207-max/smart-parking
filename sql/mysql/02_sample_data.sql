-- =====================================================================
-- SMART PARKING MANAGEMENT SYSTEM — Sample Data (DML)
-- =====================================================================
USE smart_parking_system;

-- 1. PARKING LOTS
INSERT INTO parking_lot (lot_name, location, total_floors, total_slots, contact_number) VALUES
('Central Mall Parking',   'MG Road, Bengaluru',      3, 120, '9845012345'),
('Tech Park Parking',      'Whitefield, Bengaluru',   2, 80,  '9845098765'),
('Railway Station Parking','City Railway Station',    1, 60,  '9845011122');

-- 2. CUSTOMERS
INSERT INTO customer (full_name, email, phone, password_hash, registered_on) VALUES
('Rohan Sharma',   'rohan.sharma@mail.com',  '9900011111', 'hash_pw_1', '2025-01-10'),
('Ananya Iyer',    'ananya.iyer@mail.com',   '9900022222', 'hash_pw_2', '2025-01-15'),
('Vikram Rao',     'vikram.rao@mail.com',    '9900033333', 'hash_pw_3', '2025-02-02'),
('Sneha Kulkarni', 'sneha.k@mail.com',       '9900044444', 'hash_pw_4', '2025-02-20'),
('Arjun Mehta',    'arjun.mehta@mail.com',   '9900055555', 'hash_pw_5', '2025-03-05'),
('Priya Nair',     'priya.nair@mail.com',    '9900066666', 'hash_pw_6', '2025-03-18'),
('Karan Verma',    'karan.verma@mail.com',   '9900077777', 'hash_pw_7', '2025-04-01'),
('Divya Reddy',    'divya.reddy@mail.com',   '9900088888', 'hash_pw_8', '2025-04-12');

-- 3. STAFF
INSERT INTO staff (lot_id, full_name, designation, shift, phone) VALUES
(1, 'Suresh Kumar',   'Manager',    'Morning', '9880011111'),
(1, 'Manoj Pillai',   'Attendant',  'Evening', '9880022222'),
(2, 'Ravi Teja',      'Manager',    'Morning', '9880033333'),
(2, 'Ganesh Naik',    'Security',   'Night',   '9880044444'),
(3, 'Lakshmi Devi',   'Attendant',  'Morning', '9880055555');

-- 4. PARKING SLOTS  (subset of each lot's total_slots, enough to demo)
INSERT INTO parking_slot (lot_id, slot_number, floor_number, slot_type, status) VALUES
-- Lot 1: Central Mall
(1,'A1',1,'Car','Available'),(1,'A2',1,'Car','Occupied'),(1,'A3',1,'Car','Available'),
(1,'A4',1,'Handicap','Available'),(1,'B1',2,'Bike','Available'),(1,'B2',2,'Bike','Occupied'),
(1,'B3',2,'EV','Available'),(1,'C1',3,'Car','Maintenance'),
-- Lot 2: Tech Park
(2,'T1',1,'Car','Occupied'),(2,'T2',1,'Car','Available'),(2,'T3',1,'EV','Available'),
(2,'T4',2,'Bike','Available'),(2,'T5',2,'Car','Reserved'),
-- Lot 3: Railway Station
(3,'R1',1,'Car','Available'),(3,'R2',1,'Bike','Occupied'),(3,'R3',1,'Car','Available'),
(3,'R4',1,'Handicap','Available');

-- 5. VEHICLES
INSERT INTO vehicle (customer_id, vehicle_number, vehicle_type, model_name) VALUES
(1, 'KA01AB1234', 'Car',  'Hyundai Creta'),
(2, 'KA02CD5678', 'Bike', 'Royal Enfield Classic'),
(3, 'KA03EF9012', 'Car',  'Maruti Swift'),
(4, 'KA04GH3456', 'EV',   'Tata Nexon EV'),
(5, 'KA05IJ7890', 'Car',  'Honda City'),
(6, 'KA06KL2345', 'Bike', 'TVS Jupiter'),
(7, 'KA07MN6789', 'Car',  'Toyota Innova'),
(8, 'KA08OP0123', 'Handicap', 'Maruti Wagon R (Modified)');

-- 6. PARKING RATES (per hour, by lot and vehicle type)
INSERT INTO parking_rate (lot_id, vehicle_type, rate_per_hour) VALUES
(1,'Car',40.00),(1,'Bike',15.00),(1,'EV',30.00),(1,'Handicap',20.00),
(2,'Car',35.00),(2,'Bike',10.00),(2,'EV',25.00),(2,'Handicap',15.00),
(3,'Car',30.00),(3,'Bike',10.00),(3,'EV',25.00),(3,'Handicap',15.00);

-- 7. BOOKINGS (advance reservations)
INSERT INTO booking (customer_id, vehicle_id, slot_id, booking_date, start_time, end_time, booking_status) VALUES
(1, 1, 2, '2026-08-20', '2026-08-20 09:00:00', '2026-08-20 13:00:00', 'Completed'),
(4, 4, 11,'2026-08-21', '2026-08-21 10:00:00', '2026-08-21 18:00:00', 'Confirmed'),
(7, 7, 9, '2026-08-22', '2026-08-22 08:30:00', '2026-08-22 20:00:00', 'Completed'),
(2, 2, 6, '2026-08-23', '2026-08-23 11:00:00', '2026-08-23 15:00:00', 'Cancelled');

-- 8. PARKING SESSIONS (actual entry/exit — mix of completed & active/walk-in)
INSERT INTO parking_session (booking_id, vehicle_id, slot_id, entry_time, exit_time, total_hours, amount_due, session_status) VALUES
(1,    1, 2,  '2026-08-20 09:05:00', '2026-08-20 13:10:00', 4.08, 163.20, 'Completed'),
(3,    7, 9,  '2026-08-22 08:35:00', '2026-08-22 19:50:00', 11.25, 393.75, 'Completed'),
(NULL, 3, 14, '2026-08-24 09:00:00', '2026-08-24 12:30:00', 3.50, 105.00, 'Completed'),
(NULL, 5, 9,  '2026-08-24 14:00:00', NULL, NULL, NULL, 'Active'),
(NULL, 6, 15, '2026-08-24 15:30:00', NULL, NULL, NULL, 'Active'),
(NULL, 2, 6,  '2026-08-25 08:00:00', '2026-08-25 09:45:00', 1.75, 26.25, 'Completed');

-- 9. PAYMENTS (one per completed session)
INSERT INTO payment (session_id, amount_paid, payment_mode, payment_date, payment_status) VALUES
(1, 163.20, 'UPI',    '2026-08-20 13:12:00', 'Paid'),
(2, 393.75, 'Card',   '2026-08-22 19:52:00', 'Paid'),
(3, 105.00, 'Cash',   '2026-08-24 12:32:00', 'Paid'),
(6, 26.25,  'Wallet', '2026-08-25 09:47:00', 'Paid');
