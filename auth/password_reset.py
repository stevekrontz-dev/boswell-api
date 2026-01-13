"""
Password Reset Module
Owner: CC1
Task: W1P4 - Password Reset
"""

import secrets
import hashlib
import sys
from flask import Blueprint, request, jsonify
from . import hash_password

password_reset_bp = Blueprint('password_reset', __name__, url_prefix='/v2/auth/password-reset')


def generate_reset_token() -> str:
    """Generate a secure password reset token."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """Hash reset token using SHA256."""
    return hashlib.sha256(token.encode()).hexdigest()


def init_password_reset(get_db, get_cursor):
    """Initialize password reset routes with database access."""

    @password_reset_bp.route('/request', methods=['POST'])
    def request_reset():
        """
        Request a password reset.

        Request body:
        {
            "email": "user@example.com"
        }

        Returns:
        {
            "message": "If an account exists, a reset email has been sent"
        }

        Note: Always returns success to prevent email enumeration.
        """
        data = request.get_json() or {}
        email = data.get('email', '').strip().lower()

        if not email:
            return jsonify({'error': 'Email required'}), 400

        cur = get_cursor()
        db = get_db()

        try:
            # Look up user by email
            cur.execute(
                'SELECT id, email, name FROM users WHERE email = %s AND is_active = true',
                (email,)
            )
            user = cur.fetchone()

            # Security: Always return same response regardless of user existence
            success_message = {'message': 'If an account exists with this email, a password reset link has been sent.'}

            if not user:
                cur.close()
                return jsonify(success_message), 200

            # Generate reset token
            raw_token = generate_reset_token()
            token_hash = hash_token(raw_token)

            # Invalidate any existing tokens for this user
            cur.execute(
                'UPDATE password_reset_tokens SET used_at = NOW() WHERE user_id = %s AND used_at IS NULL',
                (str(user['id']),)
            )

            # Insert new token
            cur.execute(
                '''INSERT INTO password_reset_tokens (user_id, token_hash)
                   VALUES (%s, %s)
                   RETURNING id, expires_at''',
                (str(user['id']), token_hash)
            )
            result = cur.fetchone()
            db.commit()

            # TODO: Send email with reset link
            # For now, log token for testing (REMOVE IN PRODUCTION)
            print(f"[PASSWORD RESET] Token for {email}: {raw_token}", file=sys.stderr)
            print(f"[PASSWORD RESET] Expires: {result['expires_at']}", file=sys.stderr)

            cur.close()
            return jsonify(success_message), 200

        except Exception as e:
            db.rollback()
            cur.close()
            return jsonify({'error': f'Request failed: {str(e)}'}), 500

    @password_reset_bp.route('/confirm', methods=['POST'])
    def confirm_reset():
        """
        Confirm password reset with token.

        Request body:
        {
            "token": "reset_token_from_email",
            "password": "NewSecurePassword123"
        }

        Returns:
        {
            "message": "Password has been reset successfully"
        }
        """
        data = request.get_json() or {}
        token = data.get('token', '').strip()
        new_password = data.get('password', '')

        if not token:
            return jsonify({'error': 'Reset token required'}), 400

        if not new_password:
            return jsonify({'error': 'New password required'}), 400

        if len(new_password) < 8:
            return jsonify({'error': 'Password must be at least 8 characters'}), 400

        token_hash = hash_token(token)
        cur = get_cursor()
        db = get_db()

        try:
            # Find valid token
            cur.execute(
                '''SELECT prt.id, prt.user_id, prt.expires_at, u.email
                   FROM password_reset_tokens prt
                   JOIN users u ON prt.user_id = u.id
                   WHERE prt.token_hash = %s
                     AND prt.used_at IS NULL
                     AND prt.expires_at > NOW()''',
                (token_hash,)
            )
            token_record = cur.fetchone()

            if not token_record:
                cur.close()
                return jsonify({'error': 'Invalid or expired reset token'}), 400

            # Hash new password
            password_hash = hash_password(new_password)

            # Update user's password
            cur.execute(
                'UPDATE users SET password_hash = %s WHERE id = %s',
                (password_hash, str(token_record['user_id']))
            )

            # Mark token as used
            cur.execute(
                'UPDATE password_reset_tokens SET used_at = NOW() WHERE id = %s',
                (str(token_record['id']),)
            )

            db.commit()
            cur.close()

            print(f"[PASSWORD RESET] Password reset completed for user {token_record['email']}", file=sys.stderr)

            return jsonify({
                'message': 'Password has been reset successfully. You can now log in with your new password.'
            }), 200

        except Exception as e:
            db.rollback()
            cur.close()
            return jsonify({'error': f'Reset failed: {str(e)}'}), 500

    return password_reset_bp
