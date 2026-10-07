"""
    Database models for SQLAlchamy can be found here!
"""
import uuid
from datetime import datetime

from sqlalchemy.dialects.postgresql import UUID, CITEXT
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import DateTime, String, Integer, func, select

from core.database import Base

# helper functions
def uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

def now_col() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

# user models
class Users(Base):
    __tablename__ = "users"