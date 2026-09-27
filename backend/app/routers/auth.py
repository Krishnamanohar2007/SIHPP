from datetime import datetime, timezone
import re
from pathlib import Path
from uuid import uuid4
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import AuditLog, Project, RegistrationRequest, Role, User
from app.services.auth import current_user, hash_password, require, token_for, verify_password
from app.services.india_locations import india_state_districts

router = APIRouter(prefix="/auth", tags=["auth"])
GOV_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.(gov|gov\.in|nic\.in)$", re.I)
UPLOAD_DIR = Path("/app/uploads")

class Login(BaseModel): email: str = Field(min_length=5, max_length=255); password: str = Field(min_length=12, max_length=128)
class Review(BaseModel): reason: str | None = Field(default=None, max_length=2000); role: str | None = None; password: str | None = Field(default=None, min_length=12, max_length=128)
class Assignment(BaseModel): role: str

def audit(db, actor, action, target_type, target_id, details=None): db.add(AuditLog(actor_id=actor.id if actor else None, action=action, target_type=target_type, target_id=str(target_id), details=details or {}))
@router.get("/locations")
def locations(state: str | None = None):
    reference = india_state_districts()
    return {"states": sorted(reference), "districts": sorted(reference.get(state, [])) if state else []}
@router.post("/register", status_code=201)
async def register(official_name: str = Form(...), organization: str = Form(...), designation: str = Form(...), email: str = Form(...), employee_id: str = Form(...), state: str = Form(""), district: str = Form(""), requested_role: str = Form(...), supporting_document: UploadFile = File(...), db: Session = Depends(get_db)):
    if not GOV_EMAIL.fullmatch(email): raise HTTPException(422, "Official government email required")
    role = db.scalar(select(Role).where(Role.code == requested_role));
    if not role: raise HTTPException(422, "Invalid requested role")
    if db.scalar(select(RegistrationRequest).where(RegistrationRequest.email == email, RegistrationRequest.status == "PENDING")): raise HTTPException(409, "Pending request already exists")
    if not supporting_document.filename or Path(supporting_document.filename).suffix.lower() not in {".pdf", ".png", ".jpg", ".jpeg"}: raise HTTPException(422, "Upload PDF, PNG, or JPG document")
    content = await supporting_document.read()
    if len(content) > 5 * 1024 * 1024: raise HTTPException(413, "Document must be 5 MB or smaller")
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True); path = UPLOAD_DIR / f"{uuid4()}{Path(supporting_document.filename).suffix.lower()}"; path.write_bytes(content)
    request = RegistrationRequest(official_name=official_name, organization=organization, designation=designation, email=email.lower(), employee_id=employee_id, state=state or None, district=district or None, requested_role=requested_role, document_path=str(path)); db.add(request); db.commit(); db.refresh(request); audit(db, None, "REGISTRATION_SUBMITTED", "registration_request", request.id); db.commit()
    return {"id": request.id, "status": "PENDING"}
@router.post("/login")
def login(payload: Login, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == payload.email.lower()))
    if not user or not verify_password(payload.password, user.password_hash): raise HTTPException(401, "Invalid credentials")
    if user.status != "ACTIVE": raise HTTPException(403, "Account is not active")
    return {"access_token": token_for(user), "token_type": "bearer", "role": user.role.code}
@router.get("/me")
def me(user: User = Depends(current_user)): return {"id":user.id,"name":user.official_name,"role":user.role.code,"state":user.state,"district":user.district}
@router.get("/admin/registrations")
def pending(db: Session = Depends(get_db), admin: User = Depends(require("users.review"))): return db.scalars(select(RegistrationRequest).where(RegistrationRequest.status == "PENDING").order_by(RegistrationRequest.created_at)).all()
@router.get("/admin/registrations/{request_id}/document")
def registration_document(request_id: int, db: Session = Depends(get_db), admin: User = Depends(require("users.review"))):
    request = db.get(RegistrationRequest, request_id)
    path = Path(request.document_path).resolve() if request else None
    if not request or not path or UPLOAD_DIR.resolve() not in path.parents or not path.is_file(): raise HTTPException(404, "Document not found")
    return FileResponse(path, filename=f"registration-{request.id}{path.suffix}")
@router.get("/admin/users")
def users(db: Session = Depends(get_db), admin: User = Depends(require("users.manage"))):
    return [{"id": user.id, "official_name": user.official_name, "email": user.email, "role": user.role.code, "status": user.status, "state": user.state, "district": user.district} for user in db.scalars(select(User).order_by(User.official_name)).all()]
@router.get("/assignable-users")
def assignable_users(db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Active officials an alert can be assigned to, limited to the caller's scope."""
    statement = select(User).where(User.status == "ACTIVE")
    if user.role.code == "STATE_GOVERNMENT" and user.state:
        statement = statement.where(User.state == user.state)
    if user.role.code == "DISTRICT_ADMINISTRATION" and user.district:
        statement = statement.where(User.district == user.district)
    return [{"id": row.id, "official_name": row.official_name, "role": row.role.code, "state": row.state, "district": row.district}
            for row in db.scalars(statement.order_by(User.official_name)).all()]


@router.get("/admin/audit")
def audit_log(
    action: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    actor_id: int | None = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
    reader: User = Depends(require("audit.read")),
):
    """Filterable audit trail covering accounts, projects, alerts and models."""
    statement = select(AuditLog)
    for column, value in ((AuditLog.action, action), (AuditLog.target_type, target_type), (AuditLog.target_id, target_id), (AuditLog.actor_id, actor_id)):
        if value is not None:
            statement = statement.where(column == value)
    total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    rows = db.scalars(statement.order_by(AuditLog.created_at.desc()).offset(max(offset, 0)).limit(min(max(limit, 1), 500))).all()
    actors = {user.id: user.official_name for user in db.scalars(select(User).where(User.id.in_({row.actor_id for row in rows if row.actor_id}))).all()} if rows else {}
    return {
        "total": total,
        "items": [{
            "id": row.id, "action": row.action, "target_type": row.target_type, "target_id": row.target_id,
            "actor_id": row.actor_id, "actor_name": actors.get(row.actor_id) or ("system" if row.actor_id is None else None),
            "details": row.details, "created_at": row.created_at,
        } for row in rows],
    }


@router.get("/admin/audit/actions")
def audit_actions(db: Session = Depends(get_db), reader: User = Depends(require("audit.read"))):
    """Distinct action and target values, for populating audit filters."""
    return {
        "actions": sorted(db.scalars(select(AuditLog.action).distinct()).all()),
        "target_types": sorted(db.scalars(select(AuditLog.target_type).distinct()).all()),
    }
@router.post("/admin/registrations/{request_id}/approve")
def approve(request_id: int, payload: Review, db: Session = Depends(get_db), admin: User = Depends(require("users.review"))):
    request = db.get(RegistrationRequest, request_id)
    if not request or request.status != "PENDING": raise HTTPException(404, "Pending request not found")
    role = db.scalar(select(Role).where(Role.code == (payload.role or request.requested_role)))
    if not role or not payload.password: raise HTTPException(422, "Valid role and initial password required")
    if db.scalar(select(User).where((User.email == request.email) | (User.employee_id == request.employee_id))): raise HTTPException(409, "User already exists")
    user = User(official_name=request.official_name, organization=request.organization, designation=request.designation, email=request.email, employee_id=request.employee_id, state=request.state, district=request.district, password_hash=hash_password(payload.password), role=role); db.add(user); request.status="APPROVED"; request.reviewed_by=admin.id; request.reviewed_at=datetime.now(timezone.utc); audit(db, admin, "REGISTRATION_APPROVED", "registration_request", request.id, {"role":role.code}); db.commit(); return {"status":"APPROVED","user_id":user.id}
@router.post("/admin/registrations/{request_id}/reject")
def reject(request_id: int, payload: Review, db: Session = Depends(get_db), admin: User = Depends(require("users.review"))):
    request=db.get(RegistrationRequest,request_id)
    if not request or request.status != "PENDING": raise HTTPException(404,"Pending request not found")
    if not payload.reason: raise HTTPException(422,"Rejection reason required")
    request.status="REJECTED"; request.rejection_reason=payload.reason; request.reviewed_by=admin.id; request.reviewed_at=datetime.now(timezone.utc); audit(db,admin,"REGISTRATION_REJECTED","registration_request",request.id); db.commit(); return {"status":"REJECTED"}
@router.post("/admin/users/{user_id}/role")
def assign_role(user_id:int,payload:Assignment,db:Session=Depends(get_db),admin:User=Depends(require("users.manage"))):
    """Change a user's role.

    Two guards stop the platform locking itself out of user administration.
    Only an administrator may change roles, so a demotion that removes the last
    administrator - or the acting administrator's own access - cannot be undone
    by anyone afterwards.
    """
    user=db.get(User,user_id); role=db.scalar(select(Role).where(Role.code==payload.role))
    if not user or not role: raise HTTPException(404,"User or role not found")
    previous=user.role.code
    if previous==role.code: return {"user_id":user.id,"role":role.code}
    if previous=="ADMIN" and role.code!="ADMIN":
        if user.id==admin.id:
            raise HTTPException(409,"You cannot remove your own administrator role. Ask another administrator to do it.")
        remaining=db.scalar(select(func.count()).select_from(User).join(Role).where(Role.code=="ADMIN",User.status=="ACTIVE",User.id!=user.id)) or 0
        if remaining==0:
            raise HTTPException(409,"This is the last active administrator. Promote another administrator first.")
    user.role=role; audit(db,admin,"ROLE_CHANGED","user",user.id,{"from":previous,"to":role.code}); db.commit(); return {"user_id":user.id,"role":role.code}
@router.post("/admin/users/{user_id}/projects/{project_id}")
def assign_project(user_id:int,project_id:str,db:Session=Depends(get_db),admin:User=Depends(require("users.manage"))):
    user=db.get(User,user_id); project=db.get(Project,project_id)
    if not user or not project: raise HTTPException(404,"User or project not found")
    if user.role.code not in {"LAND_ACQUISITION_AUTHORITY", "PROJECT_IMPLEMENTING_AGENCY"}: raise HTTPException(422,"Project assignment requires authority or implementing-agency role")
    if project not in user.projects: user.projects.append(project); audit(db,admin,"PROJECT_ACCESS_ASSIGNED","user",user.id,{"project_id":project_id}); db.commit()
    return {"user_id":user.id,"project_id":project_id}
