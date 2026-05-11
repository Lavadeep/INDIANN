from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
from fastapi import Body
from pydantic import BaseModel

from .. import models, database
from .permissions import get_current_user, require_project_role_by_document, all_annotators_done
from ..schemas import EntityConsensusCuration


router = APIRouter(prefix="/curation", tags=["Curation"])


from ..schemas import (
    SRLPredicateConsensus,
    SRLRoleConsensus
)


@router.get("/document/{document_id}")
def get_document_for_curation(
    document_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user),
):
    # Permission: curator / owner / admin only
    role = require_project_role_by_document(
        document_id=document_id,
        db=db,
        current_user=current_user
    )

    if role not in ("admin", "owner", "curator"):
        raise HTTPException(
            403,
            "Not authorized for curation. You must be added as a curator for this document (not only annotator)."
        )

    # Curators (not admin/owner) can curate only after all assigned annotators have marked the document done
    if role == "curator" and not all_annotators_done(db, document_id):
        raise HTTPException(
            403,
            "Curation is available only after all annotators have marked this document as complete.",
        )

    # Load document
    doc = db.query(models.Document).filter_by(document_id=document_id).first()
    if not doc:
        raise HTTPException(404, "Document not found")

    # Load ALL entity annotations (no filtering)
    annos = (
        db.query(models.EntityAnnotation, models.User)
        .join(models.User, models.EntityAnnotation.user_id == models.User.user_id)
        .filter(models.EntityAnnotation.document_id == document_id)
        .all()
    )

    # ---------------------------
    # Group by (start, end)
    # ---------------------------
    groups = {}

    for ann, user in annos:
        key = (ann.start_offset, ann.end_offset)

        groups.setdefault(key, []).append({
            "annotation_id": ann.id,
            "label": ann.entity_label,
            "text": ann.entity_text,
            "status": ann.status,
            "annotator_id": user.user_id,
            "annotator": user.username
        })

    # ---------------------------
    # Detect conflicts
    # ---------------------------
    results = []

    for (start, end), items in groups.items():
        labels = {i["label"] for i in items if i["status"] == "pending"}

        results.append({
            "start_offset": start,
            "end_offset": end,
            "text": items[0]["text"],
            "annotations": items,
            "conflict": len(labels) > 1
        })

    return {
        "document_id": document_id,
        "content": doc.content,
        "spans": results
    }

@router.post("/entity_consensus")
def curate_entity_consensus(
    payload: EntityConsensusCuration,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Consensus-aware curation for EntityAnnotations (POS).

    Consensus is resolved at the SPAN level:
    (document_id, start_offset, end_offset)
    """

    document_id = payload.document_id
    start = payload.start_offset
    end = payload.end_offset
    action = payload.action

    # Normalize label ONCE (POS are stored lowercase)
    chosen_label = payload.label.strip().lower()

    if action not in ("approved", "rejected"):
        raise HTTPException(400, "Invalid action")

    # Permission: curator / owner / admin
    role = require_project_role_by_document(
        document_id=document_id,
        db=db,
        current_user=current_user
    )
    if role not in ("admin", "owner", "curator"):
        raise HTTPException(403, "Not authorized")
    if role == "curator" and not all_annotators_done(db, document_id):
        raise HTTPException(403, "Curation is available only after all annotators have marked this document as complete.")

    now = datetime.utcnow()

    # ----------------------------------------------------
    # 1️⃣ Fetch ALL pending annotations for this span
    # ----------------------------------------------------
    span_annotations = (
        db.query(models.EntityAnnotation)
        .filter(
            models.EntityAnnotation.document_id == document_id,
            models.EntityAnnotation.start_offset == start,
            models.EntityAnnotation.end_offset == end,
            models.EntityAnnotation.status == "pending",
        )
        .all()
    )

    if not span_annotations:
        raise HTTPException(
            status_code=404,
            detail="No pending annotations found for this span"
        )

    # ----------------------------------------------------
    # 2️⃣ Apply curator decision (all annotations at this span with matching label)
    # ----------------------------------------------------
    approved_count = 0
    rejected_count = 0

    for ann in span_annotations:
        if ann.entity_label.lower() == chosen_label:
            ann.status = action
            ann.curated_by = current_user.user_id
            ann.curated_at = now
            if action == "approved":
                approved_count += 1
            else:
                rejected_count += 1

    db.commit()

    return {
        "status": "success",
        "document_id": document_id,
        "start_offset": start,
        "end_offset": end,
        "chosen_label": chosen_label,
        "approved_count": approved_count,
        "rejected_count": rejected_count,
    }


#

@router.get("/span/document/{document_id}")
def get_spans_for_curation(
    document_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user),
):
    # Permission: curator / owner / admin
    role = require_project_role_by_document(
        document_id=document_id,
        db=db,
        current_user=current_user
    )
    if role not in ("admin", "owner", "curator"):
        raise HTTPException(403, "Not authorized for span curation")
    if role == "curator" and not all_annotators_done(db, document_id):
        raise HTTPException(403, "Curation is available only after all annotators have marked this document as complete.")

    # Load document
    doc = db.query(models.Document).filter_by(document_id=document_id).first()
    if not doc:
        raise HTTPException(404, "Document not found")

    # Load ALL span annotations (all users)
    spans = (
        db.query(models.SpanAnnotation, models.User)
        .join(models.User, models.SpanAnnotation.user_id == models.User.user_id)
        .filter(models.SpanAnnotation.document_id == document_id)
        .all()
    )

    # ---------------------------
    # Group by (start, end)
    # ---------------------------
    groups = {}

    for span, user in spans:
        key = (span.start_offset, span.end_offset)
        groups.setdefault(key, []).append({
            "span_id": span.id,
            "label": span.span_label,
            "status": span.status,
            "annotator_id": user.user_id,
            "annotator": user.username
        })

    results = []
    for (start, end), items in groups.items():
        labels = {i["label"] for i in items if i["status"] == "pending"}
        results.append({
            "start_offset": start,
            "end_offset": end,
            "text": doc.content[start:end],
            "annotations": items,
            "conflict": len(labels) > 1
        })

    return {
        "document_id": document_id,
        "content": doc.content,
        "spans": results
    }




class SpanCurationPayload(BaseModel):
    action: str


@router.post("/span/{span_id}")
def curate_span_annotation(
    span_id: int,
    payload: SpanCurationPayload,   # <-- THIS IS THE FIX
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user),
):
    span = db.query(models.SpanAnnotation).filter_by(id=span_id).first()
    if not span:
        raise HTTPException(status_code=404, detail="Span not found")

    if payload.action not in ("approved", "rejected"):
        raise HTTPException(status_code=400, detail="Invalid action")

    span.status = payload.action
    span.curated_by = current_user.user_id
    span.curated_at = datetime.utcnow()

    db.commit()

    return {
        "status": "success",
        "span_id": span_id,
        "new_status": payload.action
    }


class RelationCurationPayload(BaseModel):
    action: str


@router.post("/relation/{relation_id}")
def curate_relation_annotation(
    relation_id: int,
    payload: RelationCurationPayload,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user),
):
    if payload.action not in ("approved", "rejected"):
        raise HTTPException(400, "Invalid action")

    rel = db.query(models.RelationAnnotation).filter_by(id=relation_id).first()
    if not rel:
        raise HTTPException(404, "Relation not found")

    # permission
    role = require_project_role_by_document(
        document_id=rel.document_id,
        db=db,
        current_user=current_user
    )
    if role not in ("admin", "owner", "curator"):
        raise HTTPException(403, "Not authorized")
    if role == "curator" and not all_annotators_done(db, rel.document_id):
        raise HTTPException(403, "Curation is available only after all annotators have marked this document as complete.")

    # 🔒 HARD GUARANTEE: both spans must be approved
    span1 = db.query(models.SpanAnnotation).filter_by(id=rel.span1_id).first()
    span2 = db.query(models.SpanAnnotation).filter_by(id=rel.span2_id).first()

    if not span1 or not span2:
        raise HTTPException(400, "Relation refers to missing spans")

    if span1.status != "approved" or span2.status != "approved":
        raise HTTPException(
            409,
            "Cannot curate relation before both spans are approved"
        )

    rel.status = payload.action
    rel.curated_by = current_user.user_id
    rel.curated_at = datetime.utcnow()

    db.commit()

    return {
        "status": "success",
        "relation_id": relation_id,
        "new_status": payload.action
    }


# =========================
# SRL Curation Payloads
# =========================

class SRLPredicateConsensus(BaseModel):
    document_id: int
    start_offset: int
    end_offset: int
    label: str
    action: str


class SRLRoleConsensus(BaseModel):
    document_id: int
    predicate_id: int
    start_offset: int
    end_offset: int
    label: str
    action: str


@router.get("/srl/document/{document_id}")
def get_srl_for_curation(
    document_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user),
):
    role = require_project_role_by_document(
        document_id=document_id,
        db=db,
        current_user=current_user
    )
    if role not in ("admin", "owner", "curator"):
        raise HTTPException(403, "Not authorized")
    if role == "curator" and not all_annotators_done(db, document_id):
        raise HTTPException(403, "Curation is available only after all annotators have marked this document as complete.")

    # ---------------------------
    # Load predicates (ALL users)
    # ---------------------------
    preds = (
        db.query(models.SRLPredicate, models.User)
        .join(models.User, models.SRLPredicate.user_id == models.User.user_id)
        .filter(models.SRLPredicate.document_id == document_id)
        .all()
    )

    predicate_groups = {}
    for p, u in preds:
        key = (p.start_offset, p.end_offset)
        predicate_groups.setdefault(key, []).append({
            "predicate_id": p.id,
            "label": p.predicate_label,
            "text": p.predicate_text,
            "status": p.status,
            "annotator_id": u.user_id,
            "annotator": u.username
        })

    predicates = []
    for (start, end), items in predicate_groups.items():
        labels = {i["label"] for i in items if i["status"] == "pending"}
        predicates.append({
            "start_offset": start,
            "end_offset": end,
            "annotations": items,
            "conflict": len(labels) > 1
        })

    # ---------------------------
    # Load roles (ALL users)
    # ---------------------------
    roles = (
        db.query(models.SRLRole, models.User)
        .join(models.User, models.SRLRole.user_id == models.User.user_id)
        .filter(models.SRLRole.document_id == document_id)
        .all()
    )

    role_groups = {}
    for r, u in roles:
        key = (r.predicate_id, r.start_offset, r.end_offset)
        role_groups.setdefault(key, []).append({
            "role_id": r.id,
            "predicate_id": r.predicate_id,
            "label": r.role_label,
            "text": r.role_text,
            "status": r.status,
            "annotator_id": u.user_id,
            "annotator": u.username
        })

    roles_out = []
    for (pid, start, end), items in role_groups.items():
        labels = {i["label"] for i in items if i["status"] == "pending"}
        roles_out.append({
            "predicate_id": pid,
            "start_offset": start,
            "end_offset": end,
            "annotations": items,
            "conflict": len(labels) > 1
        })

    return {
        "document_id": document_id,
        "predicates": predicates,
        "roles": roles_out
    }


@router.post("/srl/predicate_consensus")
def curate_srl_predicate_consensus(
    payload: SRLPredicateConsensus,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user),
):
    role = require_project_role_by_document(
        document_id=payload.document_id,
        db=db,
        current_user=current_user
    )
    if role not in ("admin", "owner", "curator"):
        raise HTTPException(403, "Not authorized")
    if role == "curator" and not all_annotators_done(db, payload.document_id):
        raise HTTPException(403, "Curation is available only after all annotators have marked this document as complete.")

    if payload.action not in ("approved", "rejected"):
        raise HTTPException(400, "Invalid action")

    print("SRL CURATE REQUEST:", payload)

    preds = (
        db.query(models.SRLPredicate)
        .filter(
            models.SRLPredicate.document_id == payload.document_id,
            models.SRLPredicate.start_offset == payload.start_offset,
            models.SRLPredicate.end_offset == payload.end_offset,
            models.SRLPredicate.status == "pending"
        )
        .all()
    )

    print("MATCHING PREDICATES:", [
        (p.id, p.start_offset, p.end_offset, p.status, p.predicate_label)
        for p in preds
    ])


    if not preds:
        raise HTTPException(404, "No pending predicates found")

    now = datetime.utcnow()

    for p in preds:
        if p.predicate_label == payload.label:
            p.status = payload.action
            p.curated_by = current_user.user_id
            p.curated_at = now

    db.commit()
    return {"status": "success"}


@router.post("/srl/role_consensus")
def curate_srl_role_consensus(
    payload: SRLRoleConsensus,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user),
):
    role = require_project_role_by_document(
        document_id=payload.document_id,
        db=db,
        current_user=current_user
    )
    if role not in ("admin", "owner", "curator"):
        raise HTTPException(403, "Not authorized")
    if role == "curator" and not all_annotators_done(db, payload.document_id):
        raise HTTPException(403, "Curation is available only after all annotators have marked this document as complete.")

    if payload.action not in ("approved", "rejected"):
        raise HTTPException(400, "Invalid action")

    predicate = db.query(models.SRLPredicate).filter_by(
        id=payload.predicate_id
    ).first()

    if not predicate:
        raise HTTPException(404, "Predicate not found")

    if predicate.status != "approved":
        raise HTTPException(
            409,
            "Cannot curate roles before predicate is approved"
        )

    roles = (
        db.query(models.SRLRole)
        .filter(
            models.SRLRole.document_id == payload.document_id,
            models.SRLRole.predicate_id == payload.predicate_id,
            models.SRLRole.start_offset == payload.start_offset,
            models.SRLRole.end_offset == payload.end_offset,
            models.SRLRole.status == "pending"
        )
        .all()
    )

    if not roles:
        raise HTTPException(404, "No pending roles found")

    now = datetime.utcnow()

    for r in roles:
        if r.role_label == payload.label:
            r.status = payload.action
            r.curated_by = current_user.user_id
            r.curated_at = now

    db.commit()
    return {"status": "success"}

