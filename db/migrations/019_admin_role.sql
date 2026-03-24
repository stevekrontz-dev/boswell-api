-- Migration 019: Add admin role to users table
-- Zero-downtime: nullable boolean column, no table locks

ALTER TABLE users ADD COLUMN IF NOT EXISTS is_admin BOOLEAN DEFAULT false;

-- Grant admin to Steve
UPDATE users SET is_admin = true WHERE email = 'stevekrontz@gmail.com';
