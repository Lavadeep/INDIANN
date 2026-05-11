# backend/routes/projects.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from .. import models, database
from .permissions import get_current_user

router = APIRouter(prefix="/projects", tags=["Projects"])


@router.get("/annotatable", response_model=List[dict])
def annotatable_projects(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Return projects that the frontend should show under the 'Annotator' tab.

    Policy: only show projects where the user is assigned as an *annotator*
    on at least one document (document_members.role = 'annotator').
    """
    # Admin can see everything
    if getattr(current_user, "is_admin", False):
        rows = db.query(models.Project).all()
    else:
        rows = (
            db.query(models.Project)
            .join(models.Document, models.Document.project_id == models.Project.project_id)
            .join(models.DocumentMember, models.DocumentMember.document_id == models.Document.document_id)
            .filter(
                models.DocumentMember.role == "annotator",
                models.DocumentMember.user_ids.contains([current_user.user_id]),
            )
            .distinct()
            .all()
        )

    return [
        {
            "project_id": r.project_id,
            "project_name": r.project_name,
            "description": r.description,
            "language": r.language,
            "layer_type": r.layer_type,
            "user_id": r.user_id,
            "created_at": r.created_at,
            
        }
        for r in rows
    ]


@router.get("/curatable")
def curatable_projects(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user),
):
    # Admin sees all projects
    if current_user.is_admin:
        return db.query(models.Project).all()

    # Curator sees projects that have at least one document where they are curator
    rows = (
        db.query(models.Project)
        .join(models.Document, models.Document.project_id == models.Project.project_id)
        .join(models.DocumentMember, models.DocumentMember.document_id == models.Document.document_id)
        .filter(
            models.DocumentMember.role == "curator",
            models.DocumentMember.user_ids.contains([current_user.user_id]),
        )
        .distinct()
        .all()
    )
    return rows


