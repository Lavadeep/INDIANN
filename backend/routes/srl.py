from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
from fastapi import Body
from pydantic import BaseModel


from .. import models, database, schemas
from .permissions import get_current_user, get_document_role_for_user
from ..database import get_db

# backend/routes/srl.py
router = APIRouter(prefix="/srl", tags=["Semantic Role Labeling"])

@router.post("/predicate", response_model=schemas.SRLPredicateOut)
def create_srl_predicate(
    data: schemas.SRLPredicateCreate,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user),
):
    role = get_document_role_for_user(data.document_id, db, current_user)
    if not role:
        raise HTTPException(status_code=403, detail="You do not have access to this document")

    doc = db.query(models.Document).filter_by(
        document_id=data.document_id
    ).first()
    if not doc:
        raise HTTPException(404, "Document not found")

    completed = getattr(doc, "annotator_completed_ids", None) or []
    if completed and current_user.user_id in completed:
        raise HTTPException(
            status_code=403,
            detail="You have marked this document as complete. You can no longer change annotations.",
        )

    pred = models.SRLPredicate(
        document_id=data.document_id,
        user_id=current_user.user_id,
        start_offset=data.start_offset,
        end_offset=data.end_offset,
        predicate_label=data.predicate_label,
        predicate_text=data.predicate_text,
    )

    db.add(pred)
    db.commit()
    db.refresh(pred)
    return pred


@router.post("/role", response_model=schemas.SRLRoleOut)
def create_srl_role(
    data: schemas.SRLRoleCreate,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user),
):
    role = get_document_role_for_user(data.document_id, db, current_user)
    if not role:
        raise HTTPException(status_code=403, detail="You do not have access to this document")

    predicate = db.query(models.SRLPredicate).filter_by(
        id=data.predicate_id
    ).first()

    if not predicate:
        raise HTTPException(404, "Predicate not found")

    doc = db.query(models.Document).filter_by(document_id=data.document_id).first()
    if not doc:
        raise HTTPException(404, "Document not found")

    completed = getattr(doc, "annotator_completed_ids", None) or []
    if completed and current_user.user_id in completed:
        raise HTTPException(
            status_code=403,
            detail="You have marked this document as complete. You can no longer change annotations.",
        )

    role = models.SRLRole(
        document_id=data.document_id,
        predicate_id=data.predicate_id,
        user_id=current_user.user_id,
        start_offset=data.start_offset,
        end_offset=data.end_offset,
        role_label=data.role_label,
        role_text=data.role_text,
    )

    db.add(role)
    db.commit()
    db.refresh(role)
    return role


@router.get("/document/{document_id}")
def get_srl_annotations(
    document_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user),
):
    role = get_document_role_for_user(document_id, db, current_user)
    if not role:
        raise HTTPException(status_code=403, detail="You do not have access to this document")

    predicates = (
        db.query(models.SRLPredicate)
        .filter_by(document_id=document_id)
        .all()
    )

    roles = (
        db.query(models.SRLRole)
        .filter_by(document_id=document_id)
        .all()
    )

    if role == "annotator":
        predicates = [p for p in predicates if p.user_id == current_user.user_id and getattr(p, "status", "pending") != "rejected"]
        roles = [r for r in roles if r.user_id == current_user.user_id and getattr(r, "status", "pending") != "rejected"]

    return {"predicates": predicates, "roles": roles}

@router.delete("/predicate/{predicate_id}")
def delete_predicate(
    predicate_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    predicate = db.query(models.SRLPredicate).filter(
        models.SRLPredicate.id == predicate_id,
        models.SRLPredicate.user_id == user.user_id
    ).first()

    if not predicate:
        raise HTTPException(status_code=404, detail="Predicate not found")

    # 🔥 CASCADE DELETE ROLES
    db.query(models.SRLRole).filter(
        models.SRLRole.predicate_id == predicate_id
    ).delete(synchronize_session=False)

    # 🔥 DELETE PREDICATE
    db.delete(predicate)

    db.commit()  # 🚨 THIS IS CRITICAL

    return {"status": "deleted"}


@router.delete("/role/{role_id}")
def delete_role(
    role_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    role = db.query(models.SRLRole).filter(
        models.SRLRole.id == role_id,
        models.SRLRole.user_id == user.user_id
    ).first()

    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    db.delete(role)
    db.commit()   # 🚨 CRITICAL

    return {"status": "deleted"}
