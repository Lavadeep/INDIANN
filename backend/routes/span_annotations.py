from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from .. import models, schemas, database
from .permissions import get_current_user, get_document_role_for_user

router = APIRouter(prefix="/span_annotations", tags=["Span Annotations"])


@router.post("/", response_model=schemas.SpanAnnotationOut)
def create_span(
    span: schemas.SpanAnnotationCreate,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user),
):
    role = get_document_role_for_user(span.document_id, db, current_user)
    if not role:
        raise HTTPException(status_code=403, detail="You do not have access to this document")

    doc = db.query(models.Document).filter(models.Document.document_id == span.document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    new_span = models.SpanAnnotation(
        document_id=span.document_id,
        user_id=current_user.user_id,
        start_offset=span.start_offset,
        end_offset=span.end_offset,
        span_label=span.span_label,
        span_text=span.span_text,
    )
    db.add(new_span)
    db.commit()
    db.refresh(new_span)
    return new_span


@router.get("/{document_id}", response_model=list[schemas.SpanAnnotationOut])
def get_spans(
    document_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user),
):
    role = get_document_role_for_user(document_id, db, current_user)
    if not role:
        raise HTTPException(status_code=403, detail="You do not have access to this document")

    q = db.query(models.SpanAnnotation).filter(
        models.SpanAnnotation.document_id == document_id
    )

    if role == "annotator":
        q = q.filter(
            models.SpanAnnotation.user_id == current_user.user_id,
            models.SpanAnnotation.status != "rejected"
        )

    return q.all()


@router.delete("/{span_id}")
def delete_span(
    span_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user),
):
    span = db.query(models.SpanAnnotation).filter_by(id=span_id).first()
    if not span:
        raise HTTPException(404, "Span not found")

    # Also delete relations that reference this span
    db.query(models.RelationAnnotation).filter(
        (models.RelationAnnotation.span1_id == span_id) |
        (models.RelationAnnotation.span2_id == span_id)
    ).delete(synchronize_session=False)

    db.delete(span)
    db.commit()
    return {"status": "deleted"}
