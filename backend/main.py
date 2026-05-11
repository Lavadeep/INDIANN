import os
from fastapi import FastAPI, Depends, HTTPException, status
from sqlalchemy.orm import Session
from passlib.context import CryptContext
from . import models, schemas, database
from .database import get_db
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
# Routers
from .routes import entity_annotations
from .routes import upload
from .routes import export
from .routes import export_conllu
from .routes import dependency as dep_routes
from .routes import projects as projects_router
from .routes import span_annotations
from .routes import users
from .routes import curation
from .routes import srl
from .routes import project_labels
from .routes import document_members


# Permission helpers
from .routes.permissions import (
    get_current_user,
    admin_required,
    require_project_role_by_document,
    require_project_role_by_project,
    get_document_role_for_user,
    get_assigned_annotator_ids,
    all_annotators_done,
)

from fastapi.responses import StreamingResponse, JSONResponse
import io


# CORS origins (set CORS_ORIGINS env as comma-separated list for production, e.g. https://your-server.edu)
_cors_env = os.environ.get("CORS_ORIGINS", "").strip()
CORS_ORIGINS = [o.strip() for o in _cors_env.split(",") if o.strip()] or [
    "http://127.0.0.1:5500",
    "http://localhost:5500",
]

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)


@app.exception_handler(Exception)
def unhandled_exception_handler(request, exc):
    """Return 500 with CORS headers so the browser shows the error instead of blocking with CORS."""
    import traceback
    detail = str(exc)
    tb = traceback.format_exc()
    print(tb)  # log server-side
    return JSONResponse(
        status_code=500,
        content={"detail": detail, "hint": "If this mentions 'annotator_completed_ids', run: backend/migrations/add_annotator_completed_ids.sql"},
        headers={
            "Access-Control-Allow-Origin": request.headers.get("origin") or CORS_ORIGINS[0],
            "Access-Control-Allow-Credentials": "true",
        },
    )



# Include routers
app.include_router(entity_annotations.router)
app.include_router(upload.router)
app.include_router(export.router)
app.include_router(export_conllu.router)
app.include_router(dep_routes.router)
app.include_router(projects_router.router)
app.include_router(span_annotations.router)
app.include_router(users.router)
app.include_router(curation.router)
app.include_router(srl.router)
app.include_router(project_labels.router)
app.include_router(document_members.router)

models.Base.metadata.create_all(bind=database.engine)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def conllu_to_plain_text(conllu_text: str) -> str:
    words = []
    for line in conllu_text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        cols = line.split("\t")
        if len(cols) >= 2 and cols[0].isdigit():
            words.append(cols[1])
    return " ".join(words)

# -------------------------
# LOGIN / SIGNUP
# -------------------------

@app.post("/login")
def login(user: dict, db: Session = Depends(database.get_db)):
    username = user["username"]
    password = user["password"]

    db_user = db.query(models.User).filter(models.User.username == username).first()
    if not db_user:
        raise HTTPException(400, "User not found")

    if not pwd_context.verify(password, db_user.password_hash):
        raise HTTPException(400, "Invalid password")

    return {"status": "success", "user_id": db_user.user_id,"username": db_user.username, "is_admin": db_user.is_admin}


@app.post("/signup")
def signup(user: dict, db: Session = Depends(database.get_db)):
    username = user["username"]
    email = user["email"]
    password = user["password"]
    language1 = (user.get("language1") or "").strip().lower() or None
    language2 = (user.get("language2") or "").strip().lower() or None
    language3 = (user.get("language3") or "").strip().lower() or None

    if db.query(models.User).filter(models.User.username == username).first():
        raise HTTPException(400, "Username already taken")
    if db.query(models.User).filter(models.User.email == email).first():
        raise HTTPException(400, "Email already registered")

    hashed_pw = pwd_context.hash(password)

    new_user = models.User(
        username=username,
        email=email,
        password_hash=hashed_pw,
        language1=language1,
        language2=language2,
        language3=language3,
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return {"status": "success", "user_id": new_user.user_id, "is_admin": new_user.is_admin}


# -------------------------
# CREATE PROJECT (ADMIN)
# -------------------------

@app.post("/projects")
def create_project(
    project: dict,
    db: Session = Depends(database.get_db),
    admin: models.User = Depends(admin_required),
):
    lang = (project.get("language") or "").strip().lower()
    if lang and lang not in models.ALLOWED_LANGUAGES:
        raise HTTPException(
            status_code=400,
            detail="Language must be one of: telugu, hindi, odia, bengali, english"
        )
    new_project = models.Project(
        user_id=admin.user_id,
        project_name=project["project_name"],
        description=project.get("description", ""),
        language=lang or None,
        layer_type=project.get("layer_type", ""),
    )

    db.add(new_project)
    db.commit()
    db.refresh(new_project)

    return {"status": "success", "project_id": new_project.project_id}


# -------------------------
# LIST PROJECTS FOR USER
# -------------------------

@app.get("/projects/user/{user_id}")
def list_projects_for_user(
    user_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Returns projects that the requested user_id owns OR has document-level membership.
    """
    from sqlalchemy import or_
    projects = (
        db.query(models.Project)
        .outerjoin(models.Document, models.Document.project_id == models.Project.project_id)
        .outerjoin(models.DocumentMember, models.DocumentMember.document_id == models.Document.document_id)
        .filter(
            or_(
                models.Project.user_id == user_id,
                models.DocumentMember.user_ids.contains([user_id]),
            ),
        )
        .distinct()
        .all()
    )
    return projects



# -------------------------
# LIST DOCUMENTS (open to any authenticated user)
# -------------------------
@app.get("/projects/{project_id}/documents")
def list_documents(
    project_id: int,
    mode: str | None = None,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Return documents for a project.
    Policy: only users with access can list.
    - Admin or project owner: all documents in the project
    - Curator/annotator: only documents where they are assigned in document_members
    """
    project = db.query(models.Project).filter(models.Project.project_id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    mode_norm = (mode or "").strip().lower()

    # Admin/owner: full list
    if getattr(current_user, "is_admin", False) or project.user_id == current_user.user_id:
        docs = (
            db.query(models.Document, models.Project.layer_type)
            .join(models.Project, models.Document.project_id == models.Project.project_id)
            .filter(models.Document.project_id == project_id)
            .all()
        )
    else:
        # Assigned members only, with mode-aware role filtering
        # - annotate mode: only docs where user is an assigned annotator
        # - curate mode: only docs where user is an assigned curator
        # - unspecified/other: any membership row allows visibility
        role_filter = None
        if mode_norm == "annotate":
            role_filter = "annotator"
        elif mode_norm == "curate":
            role_filter = "curator"

        docs = (
            db.query(models.Document, models.Project.layer_type)
            .join(models.Project, models.Document.project_id == models.Project.project_id)
            .join(models.DocumentMember, models.DocumentMember.document_id == models.Document.document_id)
            .filter(
                models.Document.project_id == project_id,
                *( [models.DocumentMember.role == role_filter] if role_filter else [] ),
                models.DocumentMember.user_ids.contains([current_user.user_id]),
            )
            .distinct()
            .all()
        )

    return [
        {
            "document_id": d.Document.document_id,
            "project_id": d.Document.project_id,
            "filename": d.Document.filename,
            "file_type": d.Document.file_type,
            "content": d.Document.content,
            "uploaded_by": d.Document.uploaded_by,
            "uploaded_at": d.Document.uploaded_at,
            "layer_type": d.layer_type,   # ✨ added here
        }
        for d in docs
]

# -------------------------
# LOAD DOCUMENT (open to any authenticated user)
# -------------------------

def conllu_to_plain_text_from_content(conllu_text: str) -> str:
    sentences = []
    current_tokens = []

    for line in conllu_text.splitlines():
        line = line.strip()
        if not line:
            if current_tokens:
                sentences.append(" ".join(current_tokens))
                current_tokens = []
            continue

        if line.startswith("#"):
            continue

        parts = line.split("\t")
        if len(parts) < 2:
            continue

        token_id, form = parts[0], parts[1]

        # Skip ranges (1-2) and empty nodes (3.1)
        if "-" in token_id or "." in token_id:
            continue

        current_tokens.append(form)

    if current_tokens:
        sentences.append(" ".join(current_tokens))

    return "\n".join(sentences)



@app.get("/documents/{document_id}", response_model=schemas.DocumentOut)
def get_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    role = get_document_role_for_user(document_id, db, current_user)
    if not role:
        raise HTTPException(status_code=403, detail="You do not have access to this document")

    document = db.query(models.Document).filter(
        models.Document.document_id == document_id
    ).first()

    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    content = document.content or ""

    if document.file_type == "conllu":
        content = conllu_to_plain_text(content)

    return schemas.DocumentOut(
        document_id=document.document_id,
        project_id=document.project_id,
        filename=document.filename,
        file_type=document.file_type,
        content=content,              # ✅ ALWAYS PLAIN TEXT
        uploaded_by=document.uploaded_by,
        uploaded_at=document.uploaded_at,
    )


# -------------------------
# DOWNLOAD DOCUMENT (open to any authenticated user)
# -------------------------
@app.get("/documents/{document_id}/download")
def download_document(
    document_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Download document content.
    Policy: only users with document access may download.
    """
    doc = db.query(models.Document).filter(models.Document.document_id == document_id).first()
    if not doc:
        raise HTTPException(404, "Document not found")

    role = get_document_role_for_user(document_id, db, current_user)
    if not role:
        raise HTTPException(status_code=403, detail="You do not have access to this document")

    content = (doc.content or "").strip()
    if not content:
        content = "(Empty Document)"

    filename = doc.filename or f"document_{document_id}.txt"
    if not filename.lower().endswith(".txt"):
        filename += ".txt"

    return StreamingResponse(
        io.StringIO(content),
        media_type="text/plain",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )



# -------------------------
# DELETE DOCUMENT
# -------------------------

@app.delete("/documents/{document_id}")
def delete_document(
    document_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_project_role_by_document(
        document_id=document_id, db=db, current_user=current_user
    )

    doc = (
        db.query(models.Document)
        .filter(models.Document.document_id == document_id)
        .first()
    )
    if not doc:
        raise HTTPException(404, "Document not found")

    db.delete(doc)
    db.commit()
    return {"status": "success"}


# -------------------------
# RENAME DOCUMENT
# -------------------------

@app.put("/documents/{document_id}/rename")
def rename_document(
    document_id: int,
    payload: dict,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_project_role_by_document(
        document_id=document_id, db=db, current_user=current_user
    )

    new_name = payload.get("new_name", "").strip()
    if not new_name:
        raise HTTPException(400, "New name cannot be empty")

    doc = (
        db.query(models.Document)
        .filter(models.Document.document_id == document_id)
        .first()
    )
    doc.filename = new_name
    db.commit()
    db.refresh(doc)

    return {"status": "success", "new_name": new_name}


# -------------------------
# ANNOTATION COMPLETION (annotators mark done; curators curate only when all done)
# -------------------------

@app.get("/documents/{document_id}/annotation-status")
def get_annotation_status(
    document_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Returns completion state for the current user and document.
    Used by frontend to show "Mark as done", lock editing, and enable/disable curation.
    """
    doc = db.query(models.Document).filter(models.Document.document_id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    role = get_document_role_for_user(document_id, db, current_user)
    if not role:
        raise HTTPException(status_code=403, detail="You do not have access to this document")

    assigned_annotators = get_assigned_annotator_ids(db, document_id)
    completed = getattr(doc, "annotator_completed_ids", None) or []
    if not isinstance(completed, list):
        completed = list(completed) if completed else []
    completed_set = set(int(x) for x in completed)

    user_has_completed = current_user.user_id in completed_set
    all_done = (set(assigned_annotators) <= completed_set) if assigned_annotators else True
    is_annotator = current_user.user_id in assigned_annotators

    # Anyone who is an assigned annotator can edit only until they mark done
    can_edit = True
    if is_annotator:
        can_edit = not user_has_completed

    # Curator (or owner/admin): can curate only when all annotators have marked done
    can_curate = True
    if role in ("curator", "owner", "admin"):
        can_curate = all_done
    else:
        can_curate = False

    return {
        "role": role,
        "is_annotator": is_annotator,
        "user_has_completed": user_has_completed,
        "all_annotators_done": all_done,
        "can_edit": can_edit,
        "can_curate": can_curate,
    }


@app.post("/documents/{document_id}/mark-annotation-complete")
def mark_annotation_complete(
    document_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Annotator marks this document as done. After this they cannot add/edit/delete annotations.
    Any user assigned as annotator for this document can call this (including owner/admin if they are in the annotator list).
    """
    role = get_document_role_for_user(document_id, db, current_user)
    if not role:
        raise HTTPException(status_code=403, detail="You do not have access to this document")
    assigned_annotators = get_assigned_annotator_ids(db, document_id)
    if current_user.user_id not in assigned_annotators:
        raise HTTPException(
            status_code=403,
            detail="Only users assigned as annotators for this document can mark it complete.",
        )

    doc = db.query(models.Document).filter(models.Document.document_id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    completed = list(getattr(doc, "annotator_completed_ids", None) or [])
    if not isinstance(completed, list):
        completed = [int(x) for x in completed] if completed else []
    uid = int(current_user.user_id)
    if uid in completed:
        return {"status": "already_complete", "can_edit": False}

    completed = list(set(completed) | {uid})
    doc.annotator_completed_ids = completed
    db.commit()
    db.refresh(doc)
    return {"status": "complete", "can_edit": False}


# -------------------------
# DELETE PROJECT
# -------------------------

# Replace the existing delete_project route with this (unambiguous path)
@app.delete("/projects/{project_id}/delete")
def delete_project(
    project_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Delete a project.
    Path moved to /projects/{project_id}/delete to avoid collision with other /projects/* static routes.
    Admins can delete any project; non-admins can delete only projects they created (owner).
    """
    if current_user.is_admin:
        proj = db.query(models.Project).filter(models.Project.project_id == project_id).first()
    else:
        proj = (
            db.query(models.Project)
            .filter(models.Project.project_id == project_id, models.Project.user_id == current_user.user_id)
            .first()
        )

    if not proj:
        raise HTTPException(404, "Project not found or no permission")

    db.delete(proj)
    db.commit()
    return {"status": "success"}



# -------------------------
# RELATION ANNOTATIONS
# -------------------------
@app.post("/relation_annotations", response_model=schemas.RelationAnnotationOut)
def create_relation(
    rel: schemas.RelationAnnotationCreate,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Create a relation annotation.
    Policy: user must have document access to create.
    """
    role = get_document_role_for_user(rel.document_id, db, current_user)
    if not role:
        raise HTTPException(status_code=403, detail="You do not have access to this document")

    # 1) Validate document exists
    doc = db.query(models.Document).filter(models.Document.document_id == rel.document_id).first()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    # 2) Create relation using server-side user id (prevent spoofing)
    data = rel.dict()
    # override user id if schema includes it; otherwise model may not expect user_id in body
    data["user_id"] = current_user.user_id

    db_rel = models.RelationAnnotation(**data)
    db.add(db_rel)
    db.commit()
    db.refresh(db_rel)
    return db_rel

#list relation annotations for a document
@app.get("/relation_annotations/{document_id}", response_model=list[schemas.RelationAnnotationOut])
def get_relations(
    document_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user),
):
    role = get_document_role_for_user(document_id, db, current_user)
    if not role:
        raise HTTPException(status_code=403, detail="You do not have access to this document")

    q = db.query(models.RelationAnnotation).filter(
        models.RelationAnnotation.document_id == document_id
    )

    if role == "annotator":
        q = q.filter(
            models.RelationAnnotation.user_id == current_user.user_id,
            models.RelationAnnotation.status != "rejected"
        )

    return q.all()


#delete relation annotation
@app.delete("/relation_annotations/{relation_id}")
def delete_relation(
    relation_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user),
):
    rel = db.query(models.RelationAnnotation).filter_by(id=relation_id).first()
    if not rel:
        raise HTTPException(404, "Relation not found")

    db.delete(rel)
    db.commit()
    return {"status": "deleted"}



# Admin-only: return all projects (used by admin dashboard / project page)
@app.get("/projects/all")
def get_all_projects(
    db: Session = Depends(database.get_db),
    admin: models.User = Depends(admin_required),
):
    return db.query(models.Project).all()

# Legacy/dev endpoint (was no-auth). Keep it locked to admin to prevent bypassing assignments.
@app.get("/projects/all_noauth")
def get_all_projects_noauth(
    db: Session = Depends(database.get_db),
    admin: models.User = Depends(admin_required),
):
    return db.query(models.Project).all()


