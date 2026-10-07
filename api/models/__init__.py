"""
    Database models for SQLAlchamy can be found here!
"""
import uuid
from datetime import datetime

from sqlalchemy.dialects.postgresql import UUID, CITEXT
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import DateTime, Text, Integer, func, select

from core.database import Base

# helper functions
def uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

def now_col() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

# models

class Users(Base):
    __tablename__ = "users"

    id:                 Mapped[uuid.UUID]   = uuid_pk()

    handle:             Mapped[str]         = mapped_column(CITEXT, unique=True, nullable=False)
    email:              Mapped[str]         = mapped_column(CITEXT, unique=True, nullable=False)

    password_hashed:    Mapped[str]         = mapped_column(Text, nullable=False)