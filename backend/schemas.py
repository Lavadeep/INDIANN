from pydantic import BaseModel
from datetime import datetime
from typing import Optional

# ---------------- ENTITY ----------------
class EntityAnnotationCreate(BaseModel):
    document_id: int
    user_id: int
    start_offset: int
    end_offset: int
    entity_label: str  # ✅ match DB
    entity_text: str  # ✅ match DB

class EntityAnnotationOut(EntityAnnotationCreate):
    id: int  # ✅ match DB (was annotation_id)
    status: str  # ✅ match DB

    class Config:
        from_attributes = True

# ---------------- SPAN ----------------
class SpanAnnotationCreate(BaseModel):
    document_id: int
    user_id: int
    start_offset: int
    end_offset: int
    span_label: str
    span_text: str  # ✅ match DB

class SpanAnnotationOut(SpanAnnotationCreate):
    id: int
    status: str  # ✅ match DB

    class Config:
        from_attributes = True

# ---------------- RELATION ----------------
class RelationAnnotationCreate(BaseModel):
    document_id: int
    user_id: int
    span1_id: int
    span2_id: int
    relation_label: str  # ✅ match DB

class RelationAnnotationOut(RelationAnnotationCreate):
    id: int
    status: str  # ✅ match DB

    class Config:
        from_attributes = True


class DocumentBase(BaseModel):
    project_id: int
    filename: str
    content: str
    uploaded_by: int
    file_type: str

class DocumentCreate(DocumentBase):
    pass

class DocumentOut(BaseModel):
    document_id: int
    project_id: int
    filename: str
    file_type: str
    content: str | None
    uploaded_by: Optional[int] = None
    uploaded_at: datetime    # ✅ fix this line

    class Config:
        orm_mode = True


class ProjectCreate(BaseModel):
    project_name: str
    description: str | None = None
    language: str | None = None
    layer_type: str | None = None


class ProjectOut(BaseModel):
    project_id: int
    project_name: str
    description: str | None
    language: str | None
    layer_type: str | None
    created_at: datetime | None

    class Config:
        orm_mode = True


class EntityConsensusCuration(BaseModel):
    document_id: int
    start_offset: int
    end_offset: int
    label: str
    action: str


class SRLPredicateCreate(BaseModel):
    document_id: int
    start_offset: int
    end_offset: int
    predicate_label: str
    predicate_text: str


class SRLPredicateOut(SRLPredicateCreate):
    id: int
    user_id: int
    status: str

    class Config:
        from_attributes = True

class SRLRoleCreate(BaseModel):
    document_id: int
    predicate_id: int
    start_offset: int
    end_offset: int
    role_label: str
    role_text: str


class SRLRoleOut(SRLRoleCreate):
    id: int
    user_id: int
    status: str

    class Config:
        from_attributes = True

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


class ProjectLabelCreate(BaseModel):
    layer_type: str
    label_name: str
    description: Optional[str] = None


class ProjectLabelOut(BaseModel):
    id: int
    project_id: int
    layer_type: str
    label_name: str
    description: Optional[str]

    class Config:
        from_attributes = True