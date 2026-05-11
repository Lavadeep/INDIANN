# backend/routes/dependency.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from .. import models, database
from .permissions import get_current_user, get_document_role_for_user

router = APIRouter(prefix="/dependency_annotations", tags=["Dependency Annotations"])


@router.post("/")
def create_dependency_annotation(
    ann: dict,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Create a dependency annotation (generic). Expects JSON body with at least:
      { "document_id": int, ...other fields... }
    Server will add user_id = current_user.user_id for audit.
    Returns the created row as a dict.
    """
    document_id = ann.get("document_id")
    if document_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="document_id is required")

    role = get_document_role_for_user(document_id, db, current_user)
    if not role:
        raise HTTPException(status_code=403, detail="You do not have access to this document")

    # Validate document exists
    doc = db.query(models.Document).filter(models.Document.document_id == document_id).first()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    # Build model kwargs and enforce server-side user_id
    data = dict(ann)
    data["user_id"] = current_user.user_id

    db_ann = models.DependencyAnnotation(**data)
    db.add(db_ann)
    db.commit()
    db.refresh(db_ann)

    # Convert DB object to dict for response
    result = {c.name: getattr(db_ann, c.name) for c in db_ann.__table__.columns}
    return result


@router.get("/{document_id}")
def get_dependency_annotations(
    document_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user),
):
    role = get_document_role_for_user(document_id, db, current_user)
    if not role:
        raise HTTPException(status_code=403, detail="You do not have access to this document")

    q = db.query(models.DependencyAnnotation).filter(
        models.DependencyAnnotation.document_id == document_id
    )

    if role == "annotator":
        q = q.filter(
            models.DependencyAnnotation.user_id == current_user.user_id,
            models.DependencyAnnotation.status != "rejected"
        )

    rows = q.all()
    return [{c.name: getattr(r, c.name) for c in r.__table__.columns} for r in rows]
