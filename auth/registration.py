"""
User Registration Module
Owner: CC1
Task: W1P1 - User Registration (BLOCKING)
"""

import re
import uuid
from flask import Blueprint, request, jsonify
from . import generate_jwt, hash_password

registration_bp = Blueprint('registration', __name__, url_prefix='/v2/auth')


def validate_email(email: str) -> bool:
    """Basic email validation."""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))


def validate_password(password: str) -> tuple[bool, str]:
    """Validate password strength."""
    if len(password) < 8:
        return False, 'Password must be at least 8 characters'
    if not re.search(r'[A-Z]', password):
        return False, 'Password must contain at least one uppercase letter'
    if not re.search(r'[a-z]', password):
        return False, 'Password must contain at least one lowercase letter'
    if not re.search(r'[0-9]', password):
        return False, 'Password must contain at least one number'
    return True, ''


def init_registration(get_db, get_cursor):
    """Initialize registration with database access."""

    @registration_bp.route('/register', methods=['POST'])
    def register():
        """
        Register a new user.

        Request body:
        {
            "email": "user@example.com",
            "password": "SecurePass123",
            "name": "User Name"
        }

        Returns:
        {
            "user_id": "uuid",
            "email": "user@example.com",
            "token": "jwt_token",
            "message": "Registration successful"
        }
        """
        data = request.get_json() or {}

        # Validate required fields
        email = data.get('email', '').strip().lower()
        password = data.get('password', '')
        name = data.get('name', '').strip()

        if not email:
            return jsonify({'error': 'email is required'}), 400

        if not password:
            return jsonify({'error': 'password is required'}), 400

        if not validate_email(email):
            return jsonify({'error': 'Invalid email format'}), 400

        valid, msg = validate_password(password)
        if not valid:
            return jsonify({'error': msg}), 400

        cur = get_cursor()
        db = get_db()

        try:
            # Check if email already exists
            cur.execute('SELECT id FROM users WHERE email = %s', (email,))
            if cur.fetchone():
                cur.close()
                return jsonify({'error': 'Email already registered'}), 409

            # Create user
            user_id = str(uuid.uuid4())
            password_hash = hash_password(password)

            cur.execute(
                '''INSERT INTO users (id, email, password_hash, name, created_at)
                   VALUES (%s, %s, %s, %s, NOW())
                   RETURNING created_at''',
                (user_id, email, password_hash, name or None)
            )
            created_at = cur.fetchone()['created_at']

            db.commit()
            cur.close()

            # Generate JWT
            token = generate_jwt(user_id=user_id, email=email)

            return jsonify({
                'user_id': user_id,
                'email': email,
                'name': name or None,
                'token': token,
                'created_at': str(created_at),
                'message': 'Registration successful'
            }), 201

        except Exception as e:
            db.rollback()
            cur.close()
            return jsonify({'error': f'Registration failed: {str(e)}'}), 500

    return registration_bp
