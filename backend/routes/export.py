# backend/routes/export.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from .. import models, database
from fastapi.responses import StreamingResponse
import io, json

router = APIRouter()

# ----------------------- 1️⃣ Export ALL as SpaCy JSON -----------------------
@router.get("/export/spacy_all")
def export_spacy_all(db: Session = Depends(database.get_db)):
    docs = db.query(models.Document).all()
    output = []

    for doc in docs:
        spans = db.query(models.SpanAnnotation).filter(models.SpanAnnotation.document_id == doc.document_id).all()
        rels = db.query(models.RelationAnnotation).filter(models.RelationAnnotation.document_id == doc.document_id).all()

        # Build span list
        entities = [
            {"start": s.start_offset, "end": s.end_offset, "label": s.span_label}
            for s in spans
        ]

        # Build relations using correct field names
        relations = []
        span_map = {s.id: s for s in spans}
        for r in rels:
            head = span_map.get(r.span1_id) or db.query(models.SpanAnnotation).filter(models.SpanAnnotation.id == r.span1_id).first()
            tail = span_map.get(r.span2_id) or db.query(models.SpanAnnotation).filter(models.SpanAnnotation.id == r.span2_id).first()
            if head and tail:
                relations.append({
                    "head": {"start": head.start_offset, "end": head.end_offset, "label": head.span_label},
                    "tail": {"start": tail.start_offset, "end": tail.end_offset, "label": tail.span_label},
                    "relation": r.relation_label
                })
            else:
                print(f"[WARN] Relation {getattr(r,'id',None)} references missing spans: {r.span1_id}, {r.span2_id}")

        output.append({
            "document_id": doc.document_id,
            "project_id": doc.project_id,
            "filename": doc.filename,
            "text": doc.content or "",
            "ents": entities,
            "relations": relations
        })

    return {"total_documents": len(output), "data": output}


# ----------------------- 2️⃣ Export ALL as CoNLL -----------------------
@router.get("/export/conll_all")
def export_conll_all(db: Session = Depends(database.get_db)):
    docs = db.query(models.Document).all()
    export_lines = []

    for doc in docs:
        if not doc.content:
            continue

        spans = db.query(models.SpanAnnotation).filter(models.SpanAnnotation.document_id == doc.document_id).all()
        span_map = {(s.start_offset, s.end_offset): s.span_label for s in spans}

        text = doc.content
        offset = 0
        for word in text.split():
            start = text.find(word, offset)
            end = start + len(word)
            label = "O"
            for (s, e), tag in span_map.items():
                if start >= s and end <= e:
                    label = "B-" + tag
            export_lines.append(f"{word}\t{label}")
            offset = end

        export_lines.append("")

    return {"total_documents": len(docs), "conll_data": "\n".join(export_lines)}


# ----------------------- 3️⃣ SpaCy-style Export by Language -----------------------
@router.get("/export/spacy_lang/{language}")
def export_spacy_by_language(language: str, db: Session = Depends(database.get_db)):
    lang = language.lower().strip()
    docs = (
        db.query(models.Document)
        .join(models.Project, models.Document.project_id == models.Project.project_id)
        .filter(models.Project.language.ilike(lang))
        .options(joinedload(models.Document.project))
        .all()
    )

    output = []
    for doc in docs:
        spans = db.query(models.SpanAnnotation).filter(models.SpanAnnotation.document_id == doc.document_id).all()
        rels = db.query(models.RelationAnnotation).filter(models.RelationAnnotation.document_id == doc.document_id).all()

        entities = [{"start": s.start_offset, "end": s.end_offset, "label": s.span_label} for s in spans]

        relations = []
        span_map = {s.id: s for s in spans}
        for r in rels:
            head = span_map.get(r.span1_id) or db.query(models.SpanAnnotation).filter(models.SpanAnnotation.id == r.span1_id).first()
            tail = span_map.get(r.span2_id) or db.query(models.SpanAnnotation).filter(models.SpanAnnotation.id == r.span2_id).first()
            if head and tail:
                relations.append({
                    "head": {"start": head.start_offset, "end": head.end_offset, "label": head.span_label},
                    "tail": {"start": tail.start_offset, "end": tail.end_offset, "label": tail.span_label},
                    "relation": r.relation_label
                })
            else:
                print(f"[WARN] Relation {getattr(r,'id',None)} references missing spans: {r.span1_id}, {r.span2_id}")

        output.append({
            "document_id": doc.document_id,
            "project_id": doc.project_id,
            "filename": doc.filename,
            "language": doc.project.language if doc.project else "unknown",
            "text": doc.content or "",
            "ents": entities,
            "relations": relations
        })

    return {"language": lang, "total_documents": len(output), "data": output}


# ----------------------- 4️⃣ CoNLL-style Export by Language -----------------------
# (If needed, can add; omitted for brevity)


# ----------------------- 5️⃣ Export Span + Relation Document (fixed) -----------------------
@router.get("/export/spandoc/{document_id}")
def export_spandoc(document_id: int, db: Session = Depends(database.get_db)):
    """
    Export a single document containing:
      - Entity spans: (word, label) with offsets
      - Relations: (span1text, relationlabel, span2text)
    """
    # Fetch document
    doc = db.query(models.Document).filter(models.Document.document_id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    try:
        # ---- Spans ----
        spans = db.query(models.SpanAnnotation).filter(models.SpanAnnotation.document_id == document_id).all()
        span_map = {s.id: s for s in spans}

        entities = [{"word": s.span_text, "label": s.span_label, "id": s.id,
                     "start_offset": s.start_offset, "end_offset": s.end_offset} for s in spans]

        # ---- Relations ----
        rels = db.query(models.RelationAnnotation).filter(models.RelationAnnotation.document_id == document_id).all()

        relations = []
        for r in rels:
            span1 = span_map.get(r.span1_id) or db.query(models.SpanAnnotation).filter(models.SpanAnnotation.id == r.span1_id).first()
            span2 = span_map.get(r.span2_id) or db.query(models.SpanAnnotation).filter(models.SpanAnnotation.id == r.span2_id).first()
            if span1 and span2:
                relations.append({
                    "span1_id": span1.id,
                    "span1text": span1.span_text,
                    "span1_label": span1.span_label,
                    "span2_id": span2.id,
                    "span2text": span2.span_text,
                    "span2_label": span2.span_label,
                    "relationlabel": r.relation_label
                })
            else:
                print(f"[WARN] Relation {getattr(r,'id',None)} references missing spans: {r.span1_id}, {r.span2_id}")

        export_data = {
            "document_id": doc.document_id,
            "project_id": doc.project_id,
            "filename": doc.filename,
            "text": doc.content or "",
            "ents": entities,
            "relations": relations,
        }

        json_str = json.dumps(export_data, ensure_ascii=False, indent=2)
        file_data = io.StringIO(json_str)

        return StreamingResponse(
            file_data,
            media_type="application/json",
            headers={"Content-Disposition": f"attachment; filename=document_{doc.document_id}_spans.json"},
        )

    except Exception as e:
        print(f"[ERROR] Export failed for document {document_id}: {e}")
        raise HTTPException(status_code=500, detail="Export failed: " + str(e))


# ----------------------- 5b Export SRL Document (predicates with roles) -----------------------
@router.get("/export/srldoc/{document_id}")
def export_srldoc(document_id: int, db: Session = Depends(database.get_db)):
    """
    Export a single document SRL annotations:
      - For each predicate: id, label, text, offsets, and list of roles.
      - Each role: id, role_label, role_text, start_offset, end_offset.
    Same style as spandoc (each element with its attributes).
    """
    doc = db.query(models.Document).filter(models.Document.document_id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    try:
        preds = (
            db.query(models.SRLPredicate)
            .filter(models.SRLPredicate.document_id == document_id)
            .all()
        )
        role_list = (
            db.query(models.SRLRole)
            .filter(models.SRLRole.document_id == document_id)
            .all()
        )

        # Group roles by predicate_id
        roles_by_pred = {}
        for r in role_list:
            roles_by_pred.setdefault(r.predicate_id, []).append({
                "id": r.id,
                "role_label": r.role_label,
                "role_text": r.role_text,
                "start_offset": r.start_offset,
                "end_offset": r.end_offset,
            })

        predicates = []
        for p in preds:
            predicates.append({
                "id": p.id,
                "predicate_label": p.predicate_label,
                "predicate_text": p.predicate_text,
                "start_offset": p.start_offset,
                "end_offset": p.end_offset,
                "roles": roles_by_pred.get(p.id, []),
            })

        export_data = {
            "document_id": doc.document_id,
            "project_id": doc.project_id,
            "filename": doc.filename,
            "text": doc.content or "",
            "predicates": predicates,
        }

        json_str = json.dumps(export_data, ensure_ascii=False, indent=2)
        file_data = io.StringIO(json_str)

        return StreamingResponse(
            file_data,
            media_type="application/json",
            headers={"Content-Disposition": f"attachment; filename=document_{doc.document_id}_srl_annotations.json"},
        )

    except Exception as e:
        print(f"[ERROR] SRL export failed for document {document_id}: {e}")
        raise HTTPException(status_code=500, detail="SRL export failed: " + str(e))


# ----------------------- 6️⃣ Export single document as CoNLL BIO -----------------------
@router.get("/export/conll_doc/{document_id}")
def export_conll_doc(document_id: int, db: Session = Depends(database.get_db)):
    """
    Export a single document as token-per-line with BIO tags for spans.
    Output: token <tab> BIO-Label
    """
    doc = db.query(models.Document).filter(models.Document.document_id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    text = (doc.content or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Document has no content")

    spans = db.query(models.SpanAnnotation).filter(models.SpanAnnotation.document_id == document_id).all()
    intervals = [(s.start_offset, s.end_offset, s.span_label) for s in spans]

    out_lines = []
    offset = 0
    words = text.split()
    for w in words:
        start = text.find(w, offset)
        end = start + len(w)
        label = "O"
        for (s, e, tag) in intervals:
            if start >= s and end <= e:
                if start == s:
                    label = "B-" + tag
                else:
                    label = "I-" + tag
                break
        out_lines.append(f"{w}\t{label}")
        offset = end

    out_lines.append("")

    file_text = "\n".join(out_lines)
    file_data = io.StringIO(file_text)
    return StreamingResponse(
        file_data,
        media_type="text/plain",
        headers={"Content-Disposition": f"attachment; filename=document_{document_id}_conll.txt"}
    )


# ----------------------- 7️⃣ Export POS-tagged Document -----------------------
@router.get("/export/pos/{document_id}")
def export_pos_document(document_id: int, db: Session = Depends(database.get_db)):
    """
    Export POS annotations directly from the EntityAnnotation table.
    Returns a JSON file with {"word": <entity_text>, "pos": <entity_label>} pairs.
    """
    doc = db.query(models.Document).filter(models.Document.document_id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    entities = db.query(models.EntityAnnotation).filter(models.EntityAnnotation.document_id == document_id).all()

    tokens = [
        {"word": e.entity_text, "pos": e.entity_label}
        for e in entities
    ]

    export_data = {
        "document_id": doc.document_id,
        "project_id": doc.project_id,
        "filename": doc.filename,
        "text": doc.content or "",
        "tokens": tokens
    }

    json_str = json.dumps(export_data, ensure_ascii=False, indent=2)
    file_data = io.StringIO(json_str)

    return StreamingResponse(
        file_data,
        media_type="application/json",
        headers={
            "Content-Disposition": f"attachment; filename=document_{document_id}_pos.json"
        },
    )
