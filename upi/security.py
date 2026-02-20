"""Security helpers: tokenization, field encryption, TOTP MFA helpers."""
import os
import base64
import hashlib
from typing import Optional
from werkzeug.security import generate_password_hash, check_password_hash

try:
    from cryptography.fernet import Fernet, InvalidToken
except Exception:
    Fernet = None

import pyotp

# Fernet key should be provided via env var DB_ENCRYPTION_KEY (base64 urlsafe)

def get_fernet():
    key = os.environ.get('DB_ENCRYPTION_KEY')
    if not key or Fernet is None:
        return None
    try:
        # If user set a raw password-like key, derive a 32-byte key via SHA256 and urlsafe_b64encode
        if len(key) < 43:  # likely not a valid fernet key
            k = hashlib.sha256(key.encode('utf-8')).digest()
            fkey = base64.urlsafe_b64encode(k)
        else:
            fkey = key.encode('utf-8')
        return Fernet(fkey)
    except Exception:
        return None


def encrypt_field(plaintext: Optional[str]) -> Optional[str]:
    if plaintext is None:
        return None
    f = get_fernet()
    if f is None:
        return plaintext
    try:
        return f.encrypt(plaintext.encode('utf-8')).decode('utf-8')
    except Exception:
        return plaintext


def decrypt_field(ciphertext: Optional[str]) -> Optional[str]:
    if ciphertext is None:
        return None
    f = get_fernet()
    if f is None:
        return ciphertext
    try:
        return f.decrypt(ciphertext.encode('utf-8')).decode('utf-8')
    except Exception:
        return ciphertext


# Tokenization: one-way hash of UPI/VPA/identifier with per-repo salt
REPO_SALT = os.environ.get('TOKEN_SALT', 'default_salt_should_be_changed')

def tokenize_identifier(identifier: str) -> str:
    # deterministic one-way hash
    h = hashlib.sha256()
    h.update(REPO_SALT.encode('utf-8'))
    h.update(identifier.lower().strip().encode('utf-8'))
    return h.hexdigest()


# Password helpers (werkzeug wrappers)
def hash_password(password: str) -> str:
    return generate_password_hash(password)


def verify_password(hash_val: str, password: str) -> bool:
    return check_password_hash(hash_val, password)


# TOTP helpers
def generate_totp_secret() -> str:
    return pyotp.random_base32()


def totp_uri(secret: str, user: str, issuer: str = 'UPI-Fraud') -> str:
    return pyotp.totp.TOTP(secret).provisioning_uri(name=user, issuer_name=issuer)


def verify_totp(secret: str, token: str) -> bool:
    try:
        return pyotp.TOTP(secret).verify(token, valid_window=1)
    except Exception:
        return False
