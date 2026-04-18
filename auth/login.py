"""
User Login Module
Owner: CC1
Task: W1P2 - User Login (BLOCKING CC3)
"""

from flask import Blueprint, request, jsonify
from . import generate_jwt, verify_password, is_rate_limited

login_bp = Blueprint('login', __name__, url_prefix='/v2/auth')


def init_login(get_db, get_cursor):
    """Initialize login routes with database access."""

    @login_bp.route('/login', methods=['POST'])
    def login():
        """
        Authenticate user and return JWT.

        Request body:
        {
            "email": "user@example.com",
            "password": "SecurePass123"
        }

        Returns:
        {
            "token": "jwt_token",
            "user": {
                "id": "uuid",
                "email": "user@example.com",
                "name": "User Name"
            }
        }
        """
        # Rate limit by IP: 20 login attempts per hour. Single-tenant prod
        # realistically sees low dozens per day, so 20/hour is well above
        # the legitimate ceiling while choking a credential-stuffing run.
        ip = request.remote_addr or 'unknown'
        if is_rate_limited('auth_login', ip, limit=20, window_seconds=3600):
            return jsonify({'error': 'Too many login attempts. Try again later.'}), 429

        data = request.get_json() or {}

        email = data.get('email', '').strip().lower()
        password = data.get('password', '')

        if not email or not password:
            return jsonify({'error': 'Email and password required'}), 400

        cur = get_cursor()

        try:
            # Look up user by email. Pull both legacy and v2 hash columns —
            # migration 024 added password_hash_v2; we verify against either.
            cur.execute(
                '''SELECT id, email, password_hash, password_hash_v2, name, tenant_id, is_active
                   FROM users WHERE email = %s''',
                (email,)
            )
            user = cur.fetchone()
            cur.close()

            # Security: Same error for non-existent user AND wrong password
            # Prevents email enumeration attacks
            if not user:
                return jsonify({'error': 'Invalid credentials'}), 401

            if not user['is_active']:
                return jsonify({'error': 'Account disabled'}), 401

            # Verify against v2 (Argon2id) first, fall back to legacy. On a
            # legacy-match, we lazily upgrade the row to v2 before issuing
            # the JWT so the next login lands on the modern path.
            from . import hash_password_v2
            ok, needs_rehash = verify_password(
                password,
                legacy_hash=user.get('password_hash'),
                v2_hash=user.get('password_hash_v2'),
            )
            if not ok:
                return jsonify({'error': 'Invalid credentials'}), 401

            # Generate JWT
            token = generate_jwt(
                user_id=str(user['id']),
                email=user['email'],
                tenant_id=str(user['tenant_id']) if user['tenant_id'] else None
            )

            # Update last_login_at; opportunistically upgrade the stored hash
            # to v2 if needed.
            cur = get_cursor()
            if needs_rehash:
                try:
                    new_v2 = hash_password_v2(password)
                    cur.execute(
                        'UPDATE users SET last_login_at = NOW(), password_hash_v2 = %s WHERE id = %s',
                        (new_v2, str(user['id']))
                    )
                except Exception:
                    # If Argon2 isn't available for some reason, don't block login.
                    cur.execute(
                        'UPDATE users SET last_login_at = NOW() WHERE id = %s',
                        (str(user['id']),)
                    )
            else:
                cur.execute(
                    'UPDATE users SET last_login_at = NOW() WHERE id = %s',
                    (str(user['id']),)
                )
            get_db().commit()
            cur.close()

            return jsonify({
                'token': token,
                'user': {
                    'id': str(user['id']),
                    'email': user['email'],
                    'name': user['name']
                }
            }), 200

        except Exception as e:
            cur.close()
            return jsonify({'error': f'Login failed: {str(e)}'}), 500

    return login_bp
