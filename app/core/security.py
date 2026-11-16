from datetime import datetime, timedelta, timezone
import jwt
from pwdlib import PasswordHash
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.db import get_db
from app.models import User

password_hash = PasswordHash.recommended()
oauth2 = OAuth2PasswordBearer(tokenUrl="/api/auth/token")
def hash_password(password: str) -> str:
    return password_hash.hash(password)
def verify_password(password: str, hashed: str) -> bool:
    return password_hash.verify(password, hashed)
def create_token(user: User) -> str:
    data = {"sub": user.id, "org": user.organization_id, "role": user.role,
            "exp": datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_minutes)}
    return jwt.encode(data, settings.jwt_secret, algorithm="HS256")
def current_user(token: str = Depends(oauth2), db: Session = Depends(get_db)) -> User:
    try:
        claims = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise HTTPException(401, "Invalid or expired access token") from exc
    user = db.get(User, claims.get("sub"))
    if not user or not user.active or user.organization_id != claims.get("org"):
        raise HTTPException(401, "User is unavailable")
    return user
def require_admin(user: User = Depends(current_user)) -> User:
    if user.role not in {"admin", "owner"}:
        raise HTTPException(403, "Administrator role required")
    return user
