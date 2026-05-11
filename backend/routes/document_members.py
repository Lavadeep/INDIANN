# backend/routes/document_members.py
"""
Document-level member management: assign curators and annotators per document.
Replaces project-level curator management.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import List

from .. import models, database
from .permissions import get_current_user, _user_ids_to_ints, get_assigned_annotator_ids

router = APIRouter(prefix="/documents", tags=["Document Members"])


def _require_document_admin(document_id: int, db: Session, current_user: models.User):
    """Ensure user is admin, project owner, or document curator (can manage members)."""
    doc = db.query(models.Document).filter(models.Document.document_id == document_id).first()
    if not doc:
        raise HTTPException(404, "Document not found")

    if current_user.is_admin:
        return doc
    if doc.project_id:
        proj = db.query(models.Project).filter(models.Project.project_id == doc.project_id).first()
        if proj and proj.user_id == current_user.user_id:
            return doc

    # Check if user is curator on this document
    dm = (
        db.query(models.DocumentMember)
        .filter(
            models.DocumentMember.document_id == document_id,
            models.DocumentMember.role == "curator",
        )
        .first()
    )
    ids = _user_ids_to_ints(getattr(dm, "user_ids", None))
    if dm and current_user.user_id in ids:
        return doc

    raise HTTPException(403, "Not authorized to manage document members")


@router.get("/{document_id}/members")
def list_document_members(
    document_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    List curators and annotators for a document.
    Returns { curators: [{user_id, username}], annotators: [{user_id, username}] }
    """
    doc = _require_document_admin(document_id, db, current_user)

    rows = (
        db.query(models.DocumentMember)
        .filter(models.DocumentMember.document_id == document_id)
        .all()
    )

    curators = []
    annotators = []

    completed_ids = set()
    if getattr(doc, "annotator_completed_ids", None):
        for x in doc.annotator_completed_ids:
            try:
                completed_ids.add(int(x))
            except (TypeError, ValueError):
                pass

    for r in rows:
        users_info = []
        if r.user_ids:
            users = db.query(models.User).filter(models.User.user_id.in_(r.user_ids)).all()
            for u in users:
                info = {"user_id": u.user_id, "username": u.username}
                if r.role == "annotator":
                    info["completed"] = u.user_id in completed_ids
                users_info.append(info)
        if r.role == "curator":
            curators = users_info
        elif r.role == "annotator":
            annotators = users_info

    return {"curators": curators, "annotators": annotators}


class AnnotatorStatusUpdate(BaseModel):
    user_id: int
    completed: bool


@router.put("/{document_id}/annotator-status")
def set_annotator_completion_status(
    document_id: int,
    payload: AnnotatorStatusUpdate,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Admin/curator/owner can set an annotator's completion status for this document.
    Payload: { "user_id": int, "completed": true|false }
    """
    doc = _require_document_admin(document_id, db, current_user)
    assigned = get_assigned_annotator_ids(db, document_id)
    if payload.user_id not in assigned:
        raise HTTPException(400, "User is not an assigned annotator for this document")

    completed = list(getattr(doc, "annotator_completed_ids", None) or [])
    if not isinstance(completed, list):
        completed = [int(x) for x in completed] if completed else []
    completed_set = set(int(x) for x in completed)
    uid = int(payload.user_id)

    if payload.completed:
        completed_set.add(uid)
    else:
        completed_set.discard(uid)

    doc.annotator_completed_ids = list(completed_set)
    db.commit()
    db.refresh(doc)
    return {"status": "success", "completed": payload.completed}


@router.put("/{document_id}/members")
def set_document_members(
    document_id: int,
    payload: dict,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Set curators and/or annotators for a document.
    Payload: { "curators": [user_id, ...], "annotators": [user_id, ...] }
    Replaces existing lists. Omitted roles are left unchanged; pass empty list to clear.
    """
    doc = _require_document_admin(document_id, db, current_user)

    curators = payload.get("curators")
    annotators = payload.get("annotators")

    if curators is not None:
        curators = [int(u) for u in curators] if curators else []
        _upsert_document_role(db, document_id, doc.project_id, "curator", curators, current_user.user_id)

    if annotators is not None:
        annotators = [int(u) for u in annotators] if annotators else []
        _upsert_document_role(db, document_id, doc.project_id, "annotator", annotators, current_user.user_id)

    return {"status": "success"}


def _upsert_document_role(db: Session, document_id: int, project_id: int, role: str, user_ids: List[int], granted_by: int):
    """Create or update the document_members row for this (document, role)."""
    row = (
        db.query(models.DocumentMember)
        .filter(
            models.DocumentMember.document_id == document_id,
            models.DocumentMember.role == role,
        )
        .first()
    )
    if row:
        row.user_ids = user_ids or []
        row.granted_by = granted_by
    else:
        row = models.DocumentMember(
            document_id=document_id,
            project_id=project_id,
            role=role,
            user_ids=user_ids or [],
            granted_by=granted_by,
        )
        db.add(row)
    db.commit()
