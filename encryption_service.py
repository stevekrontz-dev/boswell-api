"""
Boswell Encryption Service
Implements envelope encryption with local AES-256-GCM master key.

Master key (BOSWELL_MASTER_KEY env var) wraps per-tenant DEKs.
No external KMS dependency — key management via Railway env vars.
"""

import os
import base64
import hashlib
import secrets
import time
from typing import Optional, Tuple
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# DEK cache with TTL (5 minutes)
DEK_CACHE_TTL = 300
_dek_cache = {}  # key_id -> (plaintext_dek, timestamp)


def _get_master_key() -> Optional[bytes]:
    """Load master key from BOSWELL_MASTER_KEY env var (base64-encoded 32 bytes)."""
    raw = os.environ.get('BOSWELL_MASTER_KEY')
    if not raw:
        return None
    try:
        key = base64.b64decode(raw)
        if len(key) != 32:
            raise ValueError(f"Master key must be 32 bytes, got {len(key)}")
        return key
    except Exception as e:
        import sys
        print(f"[ENCRYPTION] Invalid BOSWELL_MASTER_KEY: {e}", file=sys.stderr)
        return None


class EncryptionService:
    """Handles envelope encryption using local AES-256-GCM master key."""

    def __init__(self):
        """Initialize with master key from environment."""
        self.master_key = _get_master_key()
        if not self.master_key:
            raise ValueError(
                "BOSWELL_MASTER_KEY not set or invalid. "
                "Generate with: python -c \"import secrets, base64; print(base64.b64encode(secrets.token_bytes(32)).decode())\""
            )

    def generate_dek(self) -> Tuple[str, bytes, bytes]:
        """
        Generate a new Data Encryption Key (DEK).
        Returns: (key_id, wrapped_dek, plaintext_dek)

        wrapped_dek format: nonce(12) + ciphertext(48) = 60 bytes
        """
        # Generate 256-bit DEK
        plaintext_dek = secrets.token_bytes(32)

        # Generate key ID from hash
        key_id = hashlib.sha256(plaintext_dek + secrets.token_bytes(8)).hexdigest()[:16]

        # Wrap DEK using master key: AES-256-GCM(master_key, plaintext_dek)
        nonce = secrets.token_bytes(12)
        aesgcm = AESGCM(self.master_key)
        ciphertext = aesgcm.encrypt(nonce, plaintext_dek, None)
        wrapped_dek = nonce + ciphertext  # 12 + 48 = 60 bytes

        # Cache the plaintext DEK
        _dek_cache[key_id] = (plaintext_dek, time.time())

        return key_id, wrapped_dek, plaintext_dek

    def unwrap_dek(self, key_id: str, wrapped_dek: bytes) -> bytes:
        """
        Unwrap a DEK using master key.
        Uses cache if available and not expired.
        """
        # Check cache first
        if key_id in _dek_cache:
            plaintext_dek, cached_at = _dek_cache[key_id]
            if time.time() - cached_at < DEK_CACHE_TTL:
                return plaintext_dek

        # Decrypt using master key
        wrapped = bytes(wrapped_dek)
        nonce = wrapped[:12]
        ciphertext = wrapped[12:]
        aesgcm = AESGCM(self.master_key)
        plaintext_dek = aesgcm.decrypt(nonce, ciphertext, None)

        # Update cache
        _dek_cache[key_id] = (plaintext_dek, time.time())

        return plaintext_dek

    def encrypt(self, plaintext: str, dek: bytes) -> Tuple[bytes, bytes]:
        """
        Encrypt content using AES-256-GCM.
        Returns: (ciphertext, nonce)
        """
        nonce = secrets.token_bytes(12)
        aesgcm = AESGCM(dek)
        ciphertext = aesgcm.encrypt(nonce, plaintext.encode('utf-8'), None)
        return ciphertext, nonce

    def decrypt(self, ciphertext: bytes, nonce: bytes, dek: bytes) -> str:
        """
        Decrypt content using AES-256-GCM.
        Returns: plaintext string
        """
        aesgcm = AESGCM(dek)
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)
        return plaintext.decode('utf-8')

    def encrypt_with_new_dek(self, plaintext: str) -> Tuple[bytes, bytes, str, bytes]:
        """
        Encrypt content with a newly generated DEK.
        Returns: (ciphertext, nonce, key_id, wrapped_dek)
        """
        key_id, wrapped_dek, plaintext_dek = self.generate_dek()
        ciphertext, nonce = self.encrypt(plaintext, plaintext_dek)
        return ciphertext, nonce, key_id, wrapped_dek

    def decrypt_with_wrapped_dek(
        self, ciphertext: bytes, nonce: bytes, key_id: str, wrapped_dek: bytes
    ) -> str:
        """Decrypt content using a wrapped DEK."""
        plaintext_dek = self.unwrap_dek(key_id, wrapped_dek)
        return self.decrypt(ciphertext, nonce, plaintext_dek)

    def canary_test(self) -> bool:
        """
        Round-trip encryption canary test.
        Generates DEK, encrypts test data, decrypts, verifies match.
        Returns True if encryption is working correctly.
        """
        test_content = "boswell-canary-" + secrets.token_hex(8)
        try:
            ciphertext, nonce, key_id, wrapped_dek = self.encrypt_with_new_dek(test_content)
            decrypted = self.decrypt_with_wrapped_dek(ciphertext, nonce, key_id, wrapped_dek)
            return decrypted == test_content
        except Exception:
            return False

    @staticmethod
    def clear_dek_cache():
        """Clear the DEK cache (useful for testing or rotation)."""
        _dek_cache.clear()

    @staticmethod
    def get_cache_stats() -> dict:
        """Get DEK cache statistics."""
        now = time.time()
        active = sum(1 for _, (_, ts) in _dek_cache.items() if now - ts < DEK_CACHE_TTL)
        return {
            "total_cached": len(_dek_cache),
            "active": active,
            "expired": len(_dek_cache) - active,
            "ttl_seconds": DEK_CACHE_TTL
        }

    @staticmethod
    def master_key_configured() -> bool:
        """Check if master key is available in environment."""
        return _get_master_key() is not None


# Singleton instance for the app
_service_instance: Optional[EncryptionService] = None

def get_encryption_service() -> Optional[EncryptionService]:
    """Get or create the singleton encryption service.
    Returns None if master key is not configured."""
    global _service_instance
    if _service_instance is None:
        try:
            _service_instance = EncryptionService()
        except ValueError:
            return None
    return _service_instance
