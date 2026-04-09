from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet
from itsdangerous import BadSignature, URLSafeSerializer

from webapp.config import get_settings


def _fernet() -> Fernet:
    settings = get_settings()
    digest = hashlib.sha256(settings.session_secret.encode("utf-8")).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def encrypt_value(value: str) -> str:
    return _fernet().encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_value(value: str) -> str:
    return _fernet().decrypt(value.encode("utf-8")).decode("utf-8")


def session_serializer() -> URLSafeSerializer:
    settings = get_settings()
    return URLSafeSerializer(settings.session_secret, salt="shoe-mapping-session")


def decode_session_cookie(value: str) -> dict | None:
    try:
        return session_serializer().loads(value)
    except BadSignature:
        return None
