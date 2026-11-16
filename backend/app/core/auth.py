from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from typing import Optional

from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from backend.app.core.config import get_settings

_sessions: dict[str, float] = {}
TTL_SECONDS = 12 * 3600


def auth_required() -> bool:
    return bool(get_settings().app_password)


def _const_eq(left: str, right: str) -> bool:
    a, b = left.encode("utf-8"), right.encode("utf-8")
    if len(a) != len(b):
        hmac.compare_digest(a, a)
        return False
    return hmac.compare_digest(a, b)


def issue_token(password: str, username: str = "") -> str:
    expected = get_settings().app_password
    if not expected:
        return "dev"
    user = (get_settings().app_username or "aqt").strip()
    if not _const_eq((username or "").strip(), user) or not _const_eq(password, expected):
        raise HTTPException(401, "账号或密码错误")
    token = secrets.token_urlsafe(32)
    _sessions[token] = time.time() + TTL_SECONDS
    return token


def revoke_token(token: Optional[str]) -> None:
    if token:
        _sessions.pop(token, None)


def verify_token(token: Optional[str]) -> bool:
    if not auth_required():
        return True
    if not token:
        return False
    exp = _sessions.get(token)
    if exp is None or exp < time.time():
        _sessions.pop(token, None)
        return False
    return True


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not auth_required():
            return await call_next(request)
        path = request.url.path
        if path in {"/api/health", "/api/auth/login", "/api/auth/logout", "/api/auth/status"} or not path.startswith("/api"):
            return await call_next(request)
        header = request.headers.get("authorization") or ""
        token = header.removeprefix("Bearer ").strip() if header.startswith("Bearer ") else ""
        if not verify_token(token):
            return JSONResponse({"detail": "未登录"}, status_code=401)
        return await call_next(request)


def password_fingerprint() -> str:
    pwd = get_settings().app_password
    if not pwd:
        return ""
    return hashlib.sha256(pwd.encode()).hexdigest()[:8]
