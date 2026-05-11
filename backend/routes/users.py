from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_

from .. import models, database
from .permissions import get_current_user

router = APIRouter(tags=["Users"])


@router.get("/users/by-language")
def list_users_by_language(
    project_id: int = Query(...),
    role: str = Query(..., description="curator or annotator"),
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Return users filtered by project language for document member assignment.
    - curator: users where language1 = project.language (p1)
    - annotator: users where language1 OR language2 = project.language (p1, p2)
    """
    project = db.query(models.Project).filter(models.Project.project_id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")
    if not current_user.is_admin and project.user_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="Admin or project owner access required")

    if not project.language:
        return []

    proj_lang = (project.language or "").strip().lower()
    if not proj_lang:
        return []

    if role == "curator":
        users = (
            db.query(models.User)
            .filter(models.User.language1 == proj_lang)
            .all()
        )
    elif role == "annotator":
        users = (
            db.query(models.User)
            .filter(
                or_(
                    models.User.language1 == proj_lang,
                    models.User.language2 == proj_lang,
                )
            )
            .all()
        )
    else:
        raise HTTPException(400, "role must be curator or annotator")

    return [
        {"user_id": u.user_id, "username": u.username}
        for u in users
    ]


@router.get("/users")
def list_users(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Return all users (id + username only).
    Used for project member assignment dropdown.
    Admin-only.
    """

    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    users = db.query(models.User).all()

    return [
        {
            "user_id": u.user_id,
            "username": u.username,
        }
        for u in users
    ]
