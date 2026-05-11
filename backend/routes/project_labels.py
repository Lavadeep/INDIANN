from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, database
from ..schemas import ProjectLabelCreate, ProjectLabelOut
from .permissions import get_current_user, require_project_role_by_project

router = APIRouter(prefix="/projects", tags=["Project Labels"])


# ===============================
# GET LABELS FOR PROJECT
# ===============================
@router.get("/{project_id}/labels", response_model=list[ProjectLabelOut])
def get_project_labels(
    project_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user)
):
    labels = (
        db.query(models.ProjectLabel)
        .filter(
            models.ProjectLabel.project_id == project_id,
            models.ProjectLabel.is_active == True
        )
        .all()
    )
    return labels


# ===============================
# ADD LABEL (ADMIN / OWNER ONLY)
# ===============================
@router.post("/{project_id}/labels")
def create_project_label(
    project_id: int,
    payload: ProjectLabelCreate,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user)
):

    role = require_project_role_by_project(
        project_id=project_id,
        db=db,
        current_user=current_user
    )

    if role not in ("admin", "owner"):
        raise HTTPException(403, "Only admin/owner can add labels")

    new_label = models.ProjectLabel(
        project_id=project_id,
        layer_type=payload.layer_type,
        label_name=payload.label_name.strip(),
        description=payload.description,
        created_by=current_user.user_id
    )

    db.add(new_label)
    db.commit()
    db.refresh(new_label)

    return {"status": "success", "label_id": new_label.id}


# ===============================
# DELETE LABEL (SOFT DELETE)
# ===============================
@router.delete("/labels/{label_id}")
def delete_project_label(
    label_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(get_current_user)
):
    label = db.query(models.ProjectLabel).filter_by(id=label_id).first()

    if not label:
        raise HTTPException(404, "Label not found")

    role = require_project_role_by_project(
        project_id=label.project_id,
        db=db,
        current_user=current_user
    )

    if role not in ("admin", "owner"):
        raise HTTPException(403, "Not authorized")

    db.delete(label)   # ✅ HARD DELETE
    db.commit()

    return {"status": "deleted"}

