# backend/routes/permissions.py
from fastapi import Depends, HTTPException, Header, status
from sqlalchemy.orm import Session
from typing import Optional, List, Any

from .. import models, database


def _user_ids_to_ints(user_ids: Any) -> List[int]:
    """Normalize user_ids from DB (list, string '{2}', etc.) to list of ints."""
    if user_ids is None:
        return []
    if isinstance(user_ids, list):
        out = []
        for x in user_ids:
            try:
                out.append(int(x))
            except (TypeError, ValueError):
                continue
        return out
    if isinstance(user_ids, str):
        # PostgreSQL array literal e.g. "{2}" or "{2,3}"
        s = user_ids.strip("{}").strip()
        if not s:
            return []
        return [int(x.strip()) for x in s.split(",") if x.strip().isdigit()]
    return []

# Basic DB dependency (reuse existing)
def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_current_user(x_user_id: Optional[str] = Header(None), db: Session = Depends(database.get_db)) -> models.User:
    """
    Prototype auth: expects X-User-Id header containing integer user_id.
    Returns the User model or raises 401.
    """
    if not x_user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="X-User-Id header required")
    try:
        uid = int(x_user_id)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid X-User-Id header")
    user = db.query(models.User).filter(models.User.user_id == uid).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


def admin_required(current_user: models.User = Depends(get_current_user)):
    """Raise 403 if current_user is not admin."""
    if not getattr(current_user, "is_admin", False):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin privileges required")
    return current_user


def require_project_role_by_project(
    project_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user)
) -> str:
    """
    Ensure current_user is project owner or admin. Used for project-level admin actions
    (labels, upload, etc). Document-level roles are in document_members.
    """
    if getattr(current_user, "is_admin", False):
        return "admin"

    proj = db.query(models.Project).filter(models.Project.project_id == project_id).first()
    if not proj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    if proj.user_id == current_user.user_id:
        return "owner"

    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"You do not have access to project {project_id}")


def require_project_role_by_document(
    document_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user)
) -> str:
    """
    Ensure current_user has access to the document: admin, project owner, or in document_members.
    Returns role: 'admin', 'owner', 'curator', or 'annotator'.
    """
    doc = db.query(models.Document).filter(models.Document.document_id == document_id).first()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    if getattr(current_user, "is_admin", False):
        return "admin"

    proj = db.query(models.Project).filter(models.Project.project_id == doc.project_id).first()
    if proj and proj.user_id == current_user.user_id:
        return "owner"

    doc_id = int(document_id)
    uid = int(current_user.user_id)

    # 1) Document-level membership (document_members table)
    # Use DB array contains so curator/annotator is found reliably (same as projects.py)
    for role_name in ("curator", "annotator"):
        row = (
            db.query(models.DocumentMember)
            .filter(
                models.DocumentMember.document_id == doc_id,
                models.DocumentMember.role == role_name,
                models.DocumentMember.user_ids.contains([uid]),
            )
            .first()
        )
        if row:
            return role_name

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="You do not have access to this document. Ask the project owner to add you as curator for this document."
    )


def get_document_role_for_user(
    document_id: int,
    db: Session,
    current_user: models.User,
) -> str | None:
    """
    Returns user's role for the document: 'admin', 'owner', 'curator', 'annotator', or None if no access.
    Does not raise; use for filtering logic.
    """
    doc = db.query(models.Document).filter(models.Document.document_id == document_id).first()
    if not doc:
        return None

    if getattr(current_user, "is_admin", False):
        return "admin"

    proj = db.query(models.Project).filter(models.Project.project_id == doc.project_id).first()
    if proj and proj.user_id == current_user.user_id:
        return "owner"

    uid = int(current_user.user_id)
    for role_name in ("curator", "annotator"):
        row = (
            db.query(models.DocumentMember)
            .filter(
                models.DocumentMember.document_id == document_id,
                models.DocumentMember.role == role_name,
                models.DocumentMember.user_ids.contains([uid]),
            )
            .first()
        )
        if row:
            return role_name

    return None


def get_assigned_annotator_ids(db: Session, document_id: int) -> List[int]:
    """Return list of user_ids assigned as annotators for this document."""
    row = (
        db.query(models.DocumentMember)
        .filter(
            models.DocumentMember.document_id == document_id,
            models.DocumentMember.role == "annotator",
        )
        .first()
    )
    if not row or not row.user_ids:
        return []
    return _user_ids_to_ints(getattr(row, "user_ids", None))


def all_annotators_done(db: Session, document_id: int) -> bool:
    """True if document has no assigned annotators or all assigned annotators have marked done."""
    doc = db.query(models.Document).filter(models.Document.document_id == document_id).first()
    if not doc:
        return False
    assigned = get_assigned_annotator_ids(db, document_id)
    if not assigned:
        return True  # no annotators assigned → curators can curate
    completed = getattr(doc, "annotator_completed_ids", None) or []
    if not isinstance(completed, list):
        completed = _user_ids_to_ints(completed)
    return set(completed) >= set(assigned)
