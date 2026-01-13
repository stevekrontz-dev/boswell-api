"""
User Login Module
Owner: CC1
Task: W1P2 - User Login (BLOCKING CC3)
"""

from flask import Blueprint, request, jsonify
from . import generate_jwt, verify_password

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
        data = request.get_json() or {}

        email = data.get('email', '').strip().lower()
        password = data.get('password', '')

        if not email or not password:
            return jsonify({'error': 'Email and password required'}), 400

        cur = get_cursor()

        try:
            # Look up user by email
            cur.execute(
                '''SELECT id, email, password_hash, name, tenant_id, is_active
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

            # Verify password (constant-time comparison via verify_password)
            if not verify_password(password, user['password_hash']):
                return jsonify({'error': 'Invalid credentials'}), 401

            # Generate JWT
            token = generate_jwt(
                user_id=str(user['id']),
                email=user['email'],
                tenant_id=str(user['tenant_id']) if user['tenant_id'] else None
            )

            # Update last_login_at
            cur = get_cursor()
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
