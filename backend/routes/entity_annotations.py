# backend/routes/entity_annotations.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from .. import models, schemas, database
from .permissions import get_current_user, get_document_role_for_user

router = APIRouter(prefix="/entity_annotations", tags=["Entity Annotations"])


@router.post("/", response_model=schemas.EntityAnnotationOut)
def create_annotation(
    annotation: schemas.EntityAnnotationCreate,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Create an entity annotation.
    Policy: user must have document access (annotator or curator) to create.
    """
    role = get_document_role_for_user(annotation.document_id, db, current_user)
    if not role:
        raise HTTPException(status_code=403, detail="You do not have access to this document")

    doc = db.query(models.Document).filter(models.Document.document_id == annotation.document_id).first()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    # Annotators who have marked the document "done" cannot add new annotations
    completed = getattr(doc, "annotator_completed_ids", None) or []
    if completed and current_user.user_id in completed:
        raise HTTPException(
            status_code=403,
            detail="You have marked this document as complete. You can no longer change annotations.",
        )

    # Create annotation
    new_annotation = models.EntityAnnotation(
        document_id=annotation.document_id,
        user_id=current_user.user_id,   # use authenticated user for audit
        start_offset=annotation.start_offset,
        end_offset=annotation.end_offset,
        entity_label=annotation.entity_label,
        entity_text=annotation.entity_text,
    )
    db.add(new_annotation)
    db.commit()
    db.refresh(new_annotation)
    return new_annotation


@router.get("/{document_id}", response_model=list[schemas.EntityAnnotationOut])
def get_annotations(
    document_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user),
):
    role = get_document_role_for_user(document_id, db, current_user)
    if not role:
        raise HTTPException(status_code=403, detail="You do not have access to this document")

    q = db.query(models.EntityAnnotation).filter(
        models.EntityAnnotation.document_id == document_id
    )

    if role == "annotator":
        q = q.filter(
            models.EntityAnnotation.user_id == current_user.user_id,
            models.EntityAnnotation.status != "rejected"
        )

    return q.all()



@router.delete("/{annotation_id}")
def delete_entity_annotation(
    annotation_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user),
):
    ann = db.query(models.EntityAnnotation).filter_by(id=annotation_id).first()
    if not ann:
        raise HTTPException(404, "Annotation not found")

    doc = db.query(models.Document).filter(models.Document.document_id == ann.document_id).first()
    if doc:
        completed = getattr(doc, "annotator_completed_ids", None) or []
        if completed and current_user.user_id in completed:
            raise HTTPException(
                status_code=403,
                detail="You have marked this document as complete. You can no longer change annotations.",
            )

    db.delete(ann)
    db.commit()
    return {"status": "deleted"}
