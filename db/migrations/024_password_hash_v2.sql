-- 024_password_hash_v2.sql
-- Adds a second password-hash column so we can migrate users from the legacy
-- salt+SHA256 scheme to Argon2id without forcing a mass rehash (which would
-- require every existing user to reset their password).
--
-- Strategy: lazy migration.
--   - New registrations write password_hash_v2 only (password_hash left NULL).
--   - Existing users keep password_hash; on their next successful login,
--     the login path verifies against password_hash, then rehashes with
--     Argon2 and writes password_hash_v2. password_hash stays populated
--     (read-only fallback) until the column is dropped in a later migration
--     after coverage reaches ~100%.
--
-- Rollback: DROP COLUMN password_hash_v2. Legacy path continues to work
-- because password_hash was never touched.

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS password_hash_v2 TEXT NULL;

-- Drop the NOT NULL constraint on password_hash so new registrations can write
-- only password_hash_v2 (Argon2id) and leave the legacy column empty. Existing
-- rows keep their legacy hash until they log in and the lazy upgrade fires.
ALTER TABLE users
    ALTER COLUMN password_hash DROP NOT NULL;

COMMENT ON COLUMN users.password_hash_v2 IS
    'Argon2id encoded string. Preferred over legacy password_hash. Populated on new registration, or lazily on first successful login after migration 024 for legacy rows.';

COMMENT ON COLUMN users.password_hash IS
    'LEGACY: salt+SHA256. Nullable post-024. Kept as read-only fallback until legacy coverage reaches 0, then dropped.';
