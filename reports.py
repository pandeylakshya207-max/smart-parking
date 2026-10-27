"""The 17 test queries from Section 5 of the project report, run live."""

REPORT_QUERIES = [
    ("Q1", "Customers with the vehicles they own", "INNER JOIN", """
SELECT c.full_name, c.phone, v.vehicle_number, v.vehicle_type, v.model_name
FROM customer c
JOIN vehicle v ON v.customer_id = c.customer_id
ORDER BY c.full_name"""),
    ("Q2", "Available slots with their lot name", "JOIN + filter", """
SELECT pl.lot_name, ps.slot_number, ps.slot_type, ps.status
FROM parking_slot ps
JOIN parking_lot pl ON pl.lot_id = ps.lot_id
WHERE ps.status = 'Available'
ORDER BY pl.lot_name, ps.slot_number"""),
    ("Q3", "Full session detail: vehicle, customer, slot", "Multi-table JOIN", """
SELECT s.session_id, c.full_name, v.vehicle_number, pl.lot_name, sl.slot_number,
       s.entry_time, s.exit_time, s.amount_due
FROM parking_session s
JOIN vehicle v       ON v.vehicle_id = s.vehicle_id
JOIN customer c      ON c.customer_id = v.customer_id
JOIN parking_slot sl ON sl.slot_id = s.slot_id
JOIN parking_lot pl  ON pl.lot_id = sl.lot_id
ORDER BY s.entry_time"""),
    ("Q4", "Total revenue collected per lot", "JOIN + GROUP BY + aggregate", """
SELECT pl.lot_name, COUNT(p.payment_id) AS transactions, SUM(p.amount_paid) AS revenue
FROM payment p
JOIN parking_session s ON s.session_id = p.session_id
JOIN parking_slot sl   ON sl.slot_id = s.slot_id
JOIN parking_lot pl    ON pl.lot_id = sl.lot_id
GROUP BY pl.lot_name
ORDER BY revenue DESC"""),
    ("Q5", "Lots whose revenue exceeds ₹150", "GROUP BY + HAVING", """
SELECT pl.lot_name, SUM(p.amount_paid) AS revenue
FROM payment p
JOIN parking_session s ON s.session_id = p.session_id
JOIN parking_slot sl   ON sl.slot_id = s.slot_id
JOIN parking_lot pl    ON pl.lot_id = sl.lot_id
GROUP BY pl.lot_name
HAVING SUM(p.amount_paid) > 150
ORDER BY revenue DESC"""),
    ("Q6", "Slot count by vehicle type and status", "GROUP BY on 2 columns", """
SELECT slot_type, status, COUNT(*) AS slot_count
FROM parking_slot
GROUP BY slot_type, status
ORDER BY slot_type"""),
    ("Q7", "Customers with an ACTIVE parking session", "Subquery with IN", """
SELECT full_name, phone
FROM customer
WHERE customer_id IN (
    SELECT v.customer_id
    FROM vehicle v
    JOIN parking_session s ON s.vehicle_id = v.vehicle_id
    WHERE s.session_status = 'Active'
)"""),
    ("Q8", "Sessions costing more than the average", "Scalar subquery", """
SELECT session_id, vehicle_id, amount_due
FROM parking_session
WHERE amount_due > (SELECT AVG(amount_due) FROM parking_session WHERE amount_due IS NOT NULL)
ORDER BY amount_due DESC"""),
    ("Q9", "Slots never used in any session", "Correlated subquery / NOT EXISTS", """
SELECT sl.slot_id, sl.slot_number, pl.lot_name
FROM parking_slot sl
JOIN parking_lot pl ON pl.lot_id = sl.lot_id
WHERE NOT EXISTS (
    SELECT 1 FROM parking_session s WHERE s.slot_id = sl.slot_id
)"""),
    ("Q10", "Highest-paying customer overall", "GROUP BY + ORDER BY + LIMIT", """
SELECT c.full_name, SUM(p.amount_paid) AS total_spent
FROM payment p
JOIN parking_session s ON s.session_id = p.session_id
JOIN vehicle v          ON v.vehicle_id = s.vehicle_id
JOIN customer c         ON c.customer_id = v.customer_id
GROUP BY c.full_name
ORDER BY total_spent DESC
LIMIT 1"""),
    ("Q11", "Rank customers by total amount spent", "Window function", """
SELECT c.full_name,
       SUM(p.amount_paid) AS total_spent,
       RANK() OVER (ORDER BY SUM(p.amount_paid) DESC) AS spend_rank
FROM payment p
JOIN parking_session s ON s.session_id = p.session_id
JOIN vehicle v          ON v.vehicle_id = s.vehicle_id
JOIN customer c         ON c.customer_id = v.customer_id
GROUP BY c.full_name"""),
    ("Q12", "Current occupancy % per lot", "Aggregate + arithmetic", """
SELECT pl.lot_name,
       COUNT(*) AS total_slots,
       SUM(CASE WHEN ps.status='Occupied' THEN 1 ELSE 0 END) AS occupied,
       ROUND(SUM(CASE WHEN ps.status='Occupied' THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) AS occupancy_pct
FROM parking_slot ps
JOIN parking_lot pl ON pl.lot_id = ps.lot_id
GROUP BY pl.lot_name"""),
    ("Q13", "Cancelled bookings with customer and vehicle", "JOIN + WHERE", """
SELECT b.booking_id, c.full_name, v.vehicle_number, b.booking_date, b.booking_status
FROM booking b
JOIN customer c ON c.customer_id = b.customer_id
JOIN vehicle v  ON v.vehicle_id = b.vehicle_id
WHERE b.booking_status = 'Cancelled'"""),
    ("Q14", "Vehicles that used more than one lot", "GROUP BY + HAVING + JOIN", """
SELECT v.vehicle_number, COUNT(DISTINCT pl.lot_id) AS lots_used
FROM parking_session s
JOIN vehicle v      ON v.vehicle_id = s.vehicle_id
JOIN parking_slot sl ON sl.slot_id = s.slot_id
JOIN parking_lot pl  ON pl.lot_id = sl.lot_id
GROUP BY v.vehicle_number
HAVING COUNT(DISTINCT pl.lot_id) > 1"""),
    ("Q15", "Real-time Car slot availability", "View: vw_slot_availability", """
SELECT * FROM vw_slot_availability WHERE slot_type = 'Car'"""),
    ("Q16", "Who is parked right now", "View: vw_active_sessions", """
SELECT * FROM vw_active_sessions"""),
    ("Q17", "Daily revenue trend", "DATE function + GROUP BY", """
SELECT DATE(payment_date) AS pay_date, SUM(amount_paid) AS daily_revenue
FROM payment
GROUP BY DATE(payment_date)
ORDER BY pay_date"""),
]
