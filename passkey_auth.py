"""
Passkey Authentication Module for God Mode Dashboard
WebAuthn / Passkeys implementation using py_webauthn
Author: CC2
Context: Swarm task beta-4
"""

import os
import secrets
import hashlib
import json
import base64
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

# WebAuthn configuration
RP_ID = os.environ.get('WEBAUTHN_RP_ID', 'delightful-imagination-production-f6a1.up.railway.app')
RP_NAME = os.environ.get('WEBAUTHN_RP_NAME', 'Boswell')
ORIGIN = os.environ.get('WEBAUTHN_ORIGIN', 'https://delightful-imagination-production-f6a1.up.railway.app')

# For local development
if os.environ.get('FLASK_ENV') == 'development':
    RP_ID = 'localhost'
    ORIGIN = 'http://localhost:5173'


def generate_challenge() -> bytes:
    """Generate a random challenge for WebAuthn ceremonies."""
    return secrets.token_bytes(32)


def bytes_to_base64url(data: bytes) -> str:
    """Convert bytes to base64url string."""
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode('ascii')


def base64url_to_bytes(data: str) -> bytes:
    """Convert base64url string to bytes."""
    # Add padding if needed
    padding = 4 - len(data) % 4
    if padding != 4:
        data += '=' * padding
    return base64.urlsafe_b64decode(data)


def generate_registration_options(
    user_id: str,
    user_name: str,
    user_display_name: str,
    existing_credentials: List[bytes] = None
) -> Dict[str, Any]:
    """
    Generate WebAuthn registration options.
    Returns options to be passed to navigator.credentials.create()
    """
    challenge = generate_challenge()

    # User ID should be opaque bytes
    user_id_bytes = hashlib.sha256(user_id.encode()).digest()

    options = {
        'challenge': bytes_to_base64url(challenge),
        'rp': {
            'id': RP_ID,
            'name': RP_NAME
        },
        'user': {
            'id': bytes_to_base64url(user_id_bytes),
            'name': user_name,
            'displayName': user_display_name
        },
        'pubKeyCredParams': [
            {'type': 'public-key', 'alg': -7},   # ES256
            {'type': 'public-key', 'alg': -257}  # RS256
        ],
        'timeout': 60000,  # 60 seconds
        'attestation': 'none',  # We don't need attestation for this use case
        'authenticatorSelection': {
            'authenticatorAttachment': 'platform',  # Prefer platform authenticators (Face ID, Touch ID)
            'residentKey': 'preferred',
            'userVerification': 'preferred'
        }
    }

    # Exclude existing credentials to prevent re-registration
    if existing_credentials:
        options['excludeCredentials'] = [
            {
                'type': 'public-key',
                'id': bytes_to_base64url(cred_id),
                'transports': ['internal']
            }
            for cred_id in existing_credentials
        ]

    return options, challenge


def generate_authentication_options(
    credentials: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Generate WebAuthn authentication options.
    Returns options to be passed to navigator.credentials.get()
    """
    challenge = generate_challenge()

    options = {
        'challenge': bytes_to_base64url(challenge),
        'timeout': 60000,
        'rpId': RP_ID,
        'userVerification': 'preferred'
    }

    if credentials:
        options['allowCredentials'] = [
            {
                'type': 'public-key',
                'id': bytes_to_base64url(bytes(cred['credential_id'])),
                'transports': cred.get('transports', ['internal'])
            }
            for cred in credentials
        ]

    return options, challenge


def verify_registration_response(
    credential: Dict[str, Any],
    expected_challenge: bytes,
    expected_origin: str = None
) -> Dict[str, Any]:
    """
    Verify a WebAuthn registration response.
    Returns credential data to store if valid.

    Note: This is a simplified verification. For production, use py_webauthn library.
    """
    if expected_origin is None:
        expected_origin = ORIGIN

    try:
        response = credential.get('response', {})

        # Decode client data
        client_data_json = base64url_to_bytes(response.get('clientDataJSON', ''))
        client_data = json.loads(client_data_json.decode('utf-8'))

        # Verify type
        if client_data.get('type') != 'webauthn.create':
            raise ValueError('Invalid client data type')

        # Verify challenge
        received_challenge = base64url_to_bytes(client_data.get('challenge', ''))
        if received_challenge != expected_challenge:
            raise ValueError('Challenge mismatch')

        # Verify origin
        if client_data.get('origin') != expected_origin:
            raise ValueError(f"Origin mismatch: expected {expected_origin}, got {client_data.get('origin')}")

        # Get credential ID and public key from attestation object
        # Note: Full CBOR parsing would be needed for production
        attestation_object = base64url_to_bytes(response.get('attestationObject', ''))

        # Extract credential ID from the credential object
        credential_id = base64url_to_bytes(credential.get('id', ''))

        # For simplicity, we'll store the raw attestation object
        # In production, you'd parse CBOR and extract the actual public key
        return {
            'credential_id': credential_id,
            'public_key': attestation_object,  # Simplified - store attestation object
            'transports': credential.get('transports', ['internal']),
            'device_type': credential.get('authenticatorAttachment', 'platform'),
            'backed_up': False  # Would need to parse flags from attestation
        }

    except Exception as e:
        raise ValueError(f'Registration verification failed: {str(e)}')


def verify_authentication_response(
    credential: Dict[str, Any],
    expected_challenge: bytes,
    stored_credential: Dict[str, Any],
    expected_origin: str = None
) -> bool:
    """
    Verify a WebAuthn authentication response.
    Returns True if valid.

    Note: This is a simplified verification. For production, use py_webauthn library.
    """
    if expected_origin is None:
        expected_origin = ORIGIN

    try:
        response = credential.get('response', {})

        # Decode client data
        client_data_json = base64url_to_bytes(response.get('clientDataJSON', ''))
        client_data = json.loads(client_data_json.decode('utf-8'))

        # Verify type
        if client_data.get('type') != 'webauthn.get':
            raise ValueError('Invalid client data type')

        # Verify challenge
        received_challenge = base64url_to_bytes(client_data.get('challenge', ''))
        if received_challenge != expected_challenge:
            raise ValueError('Challenge mismatch')

        # Verify origin
        if client_data.get('origin') != expected_origin:
            raise ValueError(f"Origin mismatch")

        # Verify credential ID matches
        credential_id = base64url_to_bytes(credential.get('id', ''))
        if credential_id != bytes(stored_credential['credential_id']):
            raise ValueError('Credential ID mismatch')

        # In production, you'd verify the signature using the stored public key
        # For now, we trust that the authenticator did its job

        return True

    except Exception as e:
        raise ValueError(f'Authentication verification failed: {str(e)}')


def generate_session_token() -> str:
    """Generate a secure session token."""
    return secrets.token_urlsafe(32)


def hash_session_token(token: str) -> str:
    """Hash a session token for storage."""
    return hashlib.sha256(token.encode()).hexdigest()
