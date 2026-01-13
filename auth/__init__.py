"""
Auth Module for Boswell SaaS
Owner: CC1
Domain: Auth & Multi-tenancy
"""

import os
import jwt
import hashlib
import secrets
from datetime import datetime, timedelta
from functools import wraps
from flask import request, jsonify, g

# JWT Configuration
JWT_SECRET = os.environ.get('JWT_SECRET', secrets.token_hex(32))
JWT_ALGORITHM = 'HS256'
JWT_EXPIRY_HOURS = int(os.environ.get('JWT_EXPIRY_HOURS', 24))


def generate_jwt(user_id: str, email: str, tenant_id: str = None) -> str:
    """Generate a JWT token for authenticated user."""
    payload = {
        'sub': user_id,
        'email': email,
        'tenant_id': tenant_id,
        'iat': datetime.utcnow(),
        'exp': datetime.utcnow() + timedelta(hours=JWT_EXPIRY_HOURS)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_jwt(token: str) -> dict:
    """Verify and decode a JWT token."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise ValueError('Token has expired')
    except jwt.InvalidTokenError as e:
        raise ValueError(f'Invalid token: {str(e)}')


def hash_password(password: str) -> str:
    """Hash password using SHA256 with salt."""
    salt = secrets.token_hex(16)
    hashed = hashlib.sha256((salt + password).encode()).hexdigest()
    return f"{salt}:{hashed}"


def verify_password(password: str, stored_hash: str) -> bool:
    """Verify password against stored hash."""
    try:
        salt, hashed = stored_hash.split(':')
        return hashlib.sha256((salt + password).encode()).hexdigest() == hashed
    except ValueError:
        return False


def require_jwt(f):
    """Decorator to require JWT authentication."""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization', '')

        if not auth_header.startswith('Bearer '):
            return jsonify({'error': 'Authorization header required'}), 401

        token = auth_header[7:]

        try:
            payload = verify_jwt(token)
            g.current_user = payload
            return f(*args, **kwargs)
        except ValueError as e:
            return jsonify({'error': str(e)}), 401

    return decorated
