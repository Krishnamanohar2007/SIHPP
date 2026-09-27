"""JWT authentication, permission checks, and server-side project scoping."""
from datetime import datetime, timedelta, timezone
import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import Select, select
from sqlalchemy.orm import Session
from app.config import get_settings
from app.database import get_db
from app.models import Project, User, user_project_access

bearer = HTTPBearer(auto_error=True)
READ_ONLY_ROLES = {"STATE_GOVERNMENT", "POLICY_MAKER"}

def hash_password(password: str) -> str: return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
def verify_password(password: str, digest: str) -> bool: return bcrypt.checkpw(password.encode(), digest.encode())
def token_for(user: User) -> str:
    settings = get_settings(); expires = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    return jwt.encode({"sub": str(user.id), "role": user.role.code, "exp": expires}, settings.jwt_secret, algorithm=settings.jwt_algorithm)
def current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer), db: Session = Depends(get_db)) -> User:
    settings = get_settings()
    try: payload = jwt.decode(credentials.credentials, settings.jwt_secret, algorithms=[settings.jwt_algorithm]); user = db.get(User, int(payload["sub"]))
    except (jwt.PyJWTError, KeyError, ValueError): raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    if not user or user.status != "ACTIVE": raise HTTPException(status.HTTP_403_FORBIDDEN, "Account is not active")
    return user
def require(permission: str):
    def guard(user: User = Depends(current_user)) -> User:
        if user.role.code == "ADMIN" or permission in {item.code for item in user.role.permissions}: return user
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Permission denied")
    return guard
def scoped_projects(statement: Select, user: User) -> Select:
    role = user.role.code
    if role in {"ADMIN", "POLICY_MAKER"}: return statement
    if role == "STATE_GOVERNMENT": return statement.where(Project.state == user.state)
    if role == "DISTRICT_ADMINISTRATION": return statement.where(Project.district == user.district)
    if role in {"LAND_ACQUISITION_AUTHORITY", "PROJECT_IMPLEMENTING_AGENCY"}: return statement.where(Project.project_id.in_(select(user_project_access.c.project_id).where(user_project_access.c.user_id == user.id)))
    return statement.where(False)
