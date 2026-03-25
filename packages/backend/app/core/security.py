from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Union
from jose import jwt
import base64
import hashlib
from cryptography.fernet import Fernet
from app.core.config import settings

# Derive a fixed-length 32-byte key from the ENCRYPTION_KEY setting
# Fernet requires a 32-byte urlsafe base64-encoded key.
_key_hash = hashlib.sha256(settings.ENCRYPTION_KEY.encode()).digest()
_fernet_key = base64.urlsafe_b64encode(_key_hash)
fernet = Fernet(_fernet_key)

# JWT configuration
SECRET_KEY = settings.JWT_SECRET
ALGORITHM = settings.JWT_ALGORITHM


def create_access_token(
    subject: Union[str, Any], expires_delta: Optional[timedelta] = None
) -> str:
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=settings.JWT_ACCESS_EXPIRE_MINUTES
        )
    to_encode = {"exp": expire, "sub": str(subject), "type": "access"}
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def create_refresh_token(
    subject: Union[str, Any], expires_delta: Optional[timedelta] = None
) -> str:
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            days=settings.JWT_REFRESH_EXPIRE_DAYS
        )
    to_encode = {"exp": expire, "sub": str(subject), "type": "refresh"}
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def verify_access_token(token: str) -> Optional[str]:
    """Verify an access token and return the user ID if valid.

    Access tokens are short-lived (30 minutes) and used for API authentication.
    """
    try:
        decoded_token = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if decoded_token.get("type") != "access":
            return None
        return decoded_token.get("sub") if "sub" in decoded_token else None
    except jwt.JWTError:
        return None


def verify_refresh_token(token: str) -> Optional[str]:
    """Verify a refresh token and return the user ID if valid.

    Refresh tokens are long-lived (30 days) and used to obtain new access tokens.
    """
    try:
        decoded_token = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if decoded_token.get("type") != "refresh":
            return None
        return decoded_token.get("sub") if "sub" in decoded_token else None
    except jwt.JWTError:
        return None

def encrypt_token(token: str) -> str:
    return fernet.encrypt(token.encode()).decode()

def decrypt_token(token: str) -> str:
    return fernet.decrypt(token.encode()).decode()
