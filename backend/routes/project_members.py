from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import models, database
from .permissions import get_current_user, require_project_role_by_project

router = APIRouter(prefix="/projects", tags=["Project Members"])


# -------------------------------------------------
# GET project members (ADMIN ONLY)
# -------------------------------------------------
@router.get("/{project_id}/members")
def list_project_members(
    project_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user),
):
    role = require_project_role_by_project(project_id, db, current_user)
    if role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Not authorized")

    rows = (
        db.query(models.ProjectMember, models.User)
        .join(models.User, models.ProjectMember.user_id == models.User.user_id)
        .filter(models.ProjectMember.project_id == project_id)
        .all()
    )

    return [
        {
            "member_id": pm.member_id,
            "user_id": u.user_id,
            "username": u.username,
            "role": pm.role,
        }
        for pm, u in rows
    ]


# -------------------------------------------------
# ADD project member (ADMIN ONLY)
# -------------------------------------------------
@router.post("/{project_id}/members")
def add_project_member(
    project_id: int,
    payload: dict,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user),
):
    role = require_project_role_by_project(project_id, db, current_user)
    if role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Not authorized")

    user_id = payload.get("user_id")
    member_role = payload.get("role", "curator")

    if member_role not in ("curator", "annotator"):
        raise HTTPException(400, "Invalid role")

    exists = (
        db.query(models.ProjectMember)
        .filter_by(project_id=project_id, user_id=user_id)
        .first()
    )
    if exists:
        raise HTTPException(400, "User already a member")

    pm = models.ProjectMember(
        project_id=project_id,
        user_id=user_id,
        role=member_role,
    )

    db.add(pm)
    db.commit()
    db.refresh(pm)

    return {"status": "success", "member_id": pm.member_id}


# -------------------------------------------------
# REMOVE project member (ADMIN ONLY)
# -------------------------------------------------
@router.delete("/members/{member_id}")
def remove_project_member(
    member_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user),
):
    pm = db.query(models.ProjectMember).filter_by(member_id=member_id).first()
    if not pm:
        raise HTTPException(404, "Member not found")

    role = require_project_role_by_project(pm.project_id, db, current_user)
    if role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Not authorized")

    if pm.role == "owner":
        raise HTTPException(400, "Cannot remove project owner")

    db.delete(pm)
    db.commit()

    return {"status": "deleted"}
