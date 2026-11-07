-- =====================================================================
-- SMART PARKING MANAGEMENT SYSTEM
-- Staff login accounts (table staff_account is created in 01_schema.sql)
-- Demo password for every account: staff@123  (stored as a salted
-- PBKDF2 hash — the plain password is never stored)
-- =====================================================================
USE smart_parking_system;

INSERT INTO staff_account (staff_id, username, password_hash) VALUES
(1, 'suresh.kumar', 'pbkdf2:sha256:100000$hNkTTuKUXIZD68X2$122ebd5415f2efddb728edb2a46787e0d1601bd439dfdc493467e3c3f3362490'),
(2, 'manoj.pillai', 'pbkdf2:sha256:100000$TEFOtG0DcIQEbgUd$72bcd772331f848848575414fca3f50ee0be7850cf26777e2341033296ff82cd'),
(3, 'ravi.teja', 'pbkdf2:sha256:100000$p3ti2IhRmVB74qlT$adc5229e6223d1be0fcd371c444a8ede554d2f641ab54c7d997bca3795feea15'),
(4, 'ganesh.naik', 'pbkdf2:sha256:100000$2BZCNrcmCseBV450$cb2a47a1d0ce12163c2b4d342c9b0bd3084e5fcdb62a2ef42480d96afe9f6d37'),
(5, 'lakshmi.devi', 'pbkdf2:sha256:100000$QsqSp3dGxF0JiCDU$a9ba4ce819c492407d0307abd74f516967c1f630eac219b6da98603ce376485f');
