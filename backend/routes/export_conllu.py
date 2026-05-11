from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from fastapi.responses import StreamingResponse
import io

from .. import models, database

router = APIRouter(prefix="/export", tags=["Export"])

# ------------------------------------------------------------
# UTILITIES (used by GENERATED export)
# ------------------------------------------------------------

def compute_sentences(text: str):
    # deterministic, simple (matches frontend assumption)
    return [s.strip() for s in text.split("\n") if s.strip()]

def simple_tokenize(sent: str):
    return [t for t in sent.split() if t]


# ============================================================
# 1️⃣ MERGED CoNLL-U (Option 3 — OLD & CORRECT)
#    Only for documents uploaded as .conllu
# ============================================================
@router.get("/conllu/{document_id}")
def export_merged_conllu(
    document_id: int,
    db: Session = Depends(database.get_db),
):
    """
    Merge POS + dependency annotations back into the ORIGINAL uploaded CoNLL-U.
    - Preserves comments, sentence boundaries, token IDs
    - Updates only UPOS / XPOS / HEAD / DEPREL
    - Returns PLAIN TEXT (.conllu)
    """

    doc = db.query(models.Document).filter(
        models.Document.document_id == document_id
    ).first()

    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    if doc.file_type != "conllu":
        raise HTTPException(status_code=400, detail="Not a CoNLL-U document")

    original_lines = (doc.content or "").splitlines()

    # Load annotations
    pos_annos = db.query(models.EntityAnnotation).filter(
        models.EntityAnnotation.document_id == document_id
    ).all()

    dep_annos = {
        d.token_index: d
        for d in db.query(models.DependencyAnnotation).filter(
            models.DependencyAnnotation.document_id == document_id
        ).all()
    }

    merged_lines = []

    for line in original_lines:
        stripped = line.strip()

        # keep comments & empty lines
        if not stripped or stripped.startswith("#"):
            merged_lines.append(line)
            continue

        parts = line.split("\t")
        if len(parts) < 10:
            merged_lines.append(line)
            continue

        token_id = parts[0]

        # skip ranges & empty nodes
        if "-" in token_id or "." in token_id:
            merged_lines.append(line)
            continue

        # extract offsets from MISC
        misc = parts[9]
        start = end = None
        for f in misc.split("|"):
            if f.startswith("start="):
                try: start = int(f.replace("start=", ""))
                except: pass
            elif f.startswith("end="):
                try: end = int(f.replace("end=", ""))
                except: pass

        # ---- merge UPOS / XPOS ----
        if start is not None and end is not None:
            for a in pos_annos:
                if a.start_offset == start and a.end_offset == end:
                    parts[3] = a.entity_label
                    parts[4] = a.entity_label
                    break

        # ---- merge HEAD / DEPREL ----
        try:
            tid = int(token_id)
            if tid in dep_annos:
                parts[6] = str(dep_annos[tid].head_index)
                parts[7] = dep_annos[tid].deprel
        except:
            pass

        merged_lines.append("\t".join(parts))

    merged_text = "\n".join(merged_lines) + "\n"

    return StreamingResponse(
        io.StringIO(merged_text),
        media_type="text/plain",
        headers={
            "Content-Disposition": f"attachment; filename={doc.filename}"
        },
    )


# ============================================================
# 2️⃣ GENERATED CoNLL-U (OLD FUNCTIONALITY)
#    For txt / pdf / docx + dependency editor
# ============================================================
@router.get("/conllu/generated/{document_id}")
def export_generated_conllu(
    document_id: int,
    auto_parse: bool = Query(False),
    db: Session = Depends(database.get_db),
):
    """
    Generate a CoNLL-U from plain text + annotations.
    Returns JSON { conllu, sidecar }.
    """

    doc = db.query(models.Document).filter(
        models.Document.document_id == document_id
    ).first()

    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    text = (doc.content or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Document has no text")

    sentences = compute_sentences(text)

    # build tokens
    tokens = []
    gid = 1
    cursor = 0

    for sent in sentences:
        sent_start = text.find(sent, cursor)
        if sent_start < 0:
            sent_start = cursor

        running = 0
        for tok in simple_tokenize(sent):
            start = text.find(tok, sent_start + running)
            if start < 0:
                start = sent_start + running
            end = start + len(tok)

            tokens.append({
                "gid": gid,
                "form": tok,
                "start": start,
                "end": end
            })
            running = end - sent_start
            gid += 1

        cursor = sent_start + len(sent)

    pos_annos = db.query(models.EntityAnnotation).filter(
        models.EntityAnnotation.document_id == document_id
    ).all()

    def find_pos(start, end):
        for a in pos_annos:
            if start >= a.start_offset and end <= a.end_offset:
                return a.entity_label
        return "_"

    dep_annos = {
        d.token_index: d
        for d in db.query(models.DependencyAnnotation).filter(
            models.DependencyAnnotation.document_id == document_id
        ).all()
    }

    lines = []
    for t in tokens:
        gid = t["gid"]
        form = t["form"]
        upos = find_pos(t["start"], t["end"])
        xpos = upos if upos != "_" else "_"

        head = "_"
        deprel = "_"
        if gid in dep_annos:
            head = dep_annos[gid].head_index
            deprel = dep_annos[gid].deprel

        misc = f"start={t['start']}|end={t['end']}"
        line = f"{gid}\t{form}\t{form}\t{upos}\t{xpos}\t_\t{head}\t{deprel}\t_\t{misc}"
        lines.append(line)

    conllu_text = "\n".join(lines) + "\n"

    return {
        "conllu": conllu_text,
        "sidecar": {}
    }
