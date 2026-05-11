from sqlalchemy import Column, Integer, String, TIMESTAMP, ForeignKey, Text, func, Boolean, CheckConstraint, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import relationship
from .database import Base

ALLOWED_LANGUAGES = ("telugu", "hindi", "odia", "bengali", "english")

class User(Base):
    __tablename__ = "users"
    user_id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True)
    password_hash = Column(String, nullable=False)
    is_admin = Column(Boolean, nullable=False, server_default="false")
    language1 = Column(String(50))
    language2 = Column(String(50))
    language3 = Column(String(50))

    # Projects this user created (creator relationship on Project)
    created_projects = relationship(
        "Project",
        back_populates="creator",
        foreign_keys="[Project.user_id]"
    )

class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (
        CheckConstraint(
            "language IS NULL OR language IN ('telugu', 'hindi', 'odia', 'bengali', 'english')",
            name="project_language_allowed"
        ),
    )
    project_id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.user_id"))   # owner/creator FK
    project_name = Column(String, nullable=False)
    description = Column(Text)
    language = Column(String(50))
    layer_type = Column(String(100))
    created_at = Column(TIMESTAMP, server_default=func.now())

    # Link back to the User who created this project
    creator = relationship(
        "User",
        back_populates="created_projects",
        foreign_keys=[user_id]
    )

class Document(Base):
    __tablename__ = "documents"
    document_id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.project_id"))
    filename = Column(String(255))
    content = Column(Text)
    uploaded_by = Column(Integer, ForeignKey("users.user_id"))
    uploaded_at = Column(TIMESTAMP)
    file_type = Column(String(50))
    annotator_completed_ids = Column(ARRAY(Integer), nullable=False, default=list, server_default="{}")  # user_ids who marked "done"
    annotations = relationship("EntityAnnotation", back_populates="document", cascade="all, delete")
    document_members = relationship("DocumentMember", back_populates="document", cascade="all, delete-orphan")


class DocumentMember(Base):
    """
    Document-level assignments: curators and annotators per document.
    One row per (document_id, role) with user_ids as array.
    Row: doc_id, project_id, role, user_ids (list of uid), granted_at, granted_by
    """
    __tablename__ = "document_members"
    __table_args__ = (UniqueConstraint("document_id", "role", name="uq_document_member_doc_role"),)

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.document_id", ondelete="CASCADE"), nullable=False)
    project_id = Column(Integer, ForeignKey("projects.project_id", ondelete="CASCADE"), nullable=False)
    role = Column(String(50), nullable=False)  # 'curator' or 'annotator'
    user_ids = Column(ARRAY(Integer), nullable=False, default=list)  # list of user_id
    granted_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    granted_by = Column(Integer, ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True)

    document = relationship("Document", back_populates="document_members")
    project = relationship("Project")
    granted_by_user = relationship("User", foreign_keys=[granted_by])

# ---------------- ENTITY ----------------
class EntityAnnotation(Base):
    __tablename__ = "entity_annotations"  # ✅ match DB

    id = Column(Integer, primary_key=True, index=True)  # ✅ id not annotation_id
    document_id = Column(Integer, ForeignKey("documents.document_id", ondelete="CASCADE"))
    user_id = Column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"))
    start_offset = Column(Integer, nullable=False)
    end_offset = Column(Integer, nullable=False)
    entity_label = Column(String(100), nullable=False)
    entity_text = Column(String(255), nullable=False)
    created_at = Column(TIMESTAMP, server_default=func.now())
    status = Column(String(20), nullable=False, server_default="pending")
    document = relationship("Document", back_populates="annotations", lazy="joined")

# ---------------- SPAN ----------------
class SpanAnnotation(Base):
    __tablename__ = "span_annotations"  # ✅ match DB

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.document_id"))
    user_id = Column(Integer, ForeignKey("users.user_id"))
    start_offset = Column(Integer)
    end_offset = Column(Integer)
    span_label = Column(String(100))  # ✅ match DB
    span_text = Column(String(255))  # ✅ match DB
    status = Column(String(20), nullable=False, server_default="pending")
    document = relationship("Document")
    user = relationship("User")

# ---------------- RELATION ----------------
class RelationAnnotation(Base):
    __tablename__ = "relation_annotations"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.document_id"))
    user_id = Column(Integer, ForeignKey("users.user_id"))
    span1_id = Column(Integer, ForeignKey("span_annotations.id"))  # ✅ match DB
    span2_id = Column(Integer, ForeignKey("span_annotations.id"))  # ✅ match DB
    relation_label = Column(String(100))  # ✅ match DB
    status = Column(String(20), nullable=False, server_default="pending")
    document = relationship("Document")
    user = relationship("User")
    span1 = relationship("SpanAnnotation", foreign_keys=[span1_id])
    span2 = relationship("SpanAnnotation", foreign_keys=[span2_id])


# between tokens
class DependencyAnnotation(Base):
    __tablename__ = "dependency_annotations"
    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.document_id", ondelete="CASCADE"))
    token_index = Column(Integer, nullable=False)   # 1-based token id in exported tokenization
    head_index = Column(Integer, nullable=False)    # 0 = root
    deprel = Column(String(64), nullable=False)     # e.g., nsubj, root, obj
    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=True)
    status = Column(String(20), nullable=False, server_default="pending")
    created_at = Column(TIMESTAMP, server_default=func.now())


class SRLPredicate(Base):
    __tablename__ = "srl_predicates"

    id = Column(Integer, primary_key=True, index=True)

    document_id = Column(
        Integer,
        ForeignKey("documents.document_id", ondelete="CASCADE"),
        nullable=False
    )

    user_id = Column(
        Integer,
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False
    )

    start_offset = Column(Integer, nullable=False)
    end_offset = Column(Integer, nullable=False)

    predicate_label = Column(String(50), nullable=False, default="PRED")
    predicate_text = Column(String(255), nullable=False)

    status = Column(String(20), nullable=False, server_default="pending")
    created_at = Column(TIMESTAMP, server_default=func.now())

    document = relationship("Document")
    user = relationship("User")

    roles = relationship(
        "SRLRole",
        back_populates="predicate",
        cascade="all, delete-orphan"
    )



class SRLRole(Base):
    __tablename__ = "srl_roles"

    id = Column(Integer, primary_key=True, index=True)

    document_id = Column(
        Integer,
        ForeignKey("documents.document_id", ondelete="CASCADE"),
        nullable=False
    )

    predicate_id = Column(
        Integer,
        ForeignKey("srl_predicates.id", ondelete="CASCADE"),
        nullable=False
    )

    user_id = Column(
        Integer,
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False
    )

    start_offset = Column(Integer, nullable=False)
    end_offset = Column(Integer, nullable=False)

    role_label = Column(String(50), nullable=False)
    role_text = Column(String(255), nullable=False)

    status = Column(String(20), nullable=False, server_default="pending")
    created_at = Column(TIMESTAMP, server_default=func.now())

    predicate = relationship("SRLPredicate", back_populates="roles")
    document = relationship("Document")
    user = relationship("User")


class ProjectLabel(Base):
    __tablename__ = "project_labels"

    id = Column(Integer, primary_key=True, index=True)

    project_id = Column(
        Integer,
        ForeignKey("projects.project_id", ondelete="CASCADE"),
        nullable=False
    )

    layer_type = Column(String(50), nullable=False)
    label_name = Column(String(100), nullable=False)
    description = Column(Text)

    created_by = Column(
        Integer,
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True
    )

    created_at = Column(TIMESTAMP, server_default=func.now())
    is_active = Column(Boolean, default=True)

    project = relationship("Project")
    creator = relationship("User")
