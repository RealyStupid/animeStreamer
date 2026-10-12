"""
    Database models for SQLAlchamy can be found here!
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy.dialects.postgresql import UUID, CITEXT
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import DateTime, Text, func, Enum, ForeignKey, Integer, String, Table, Column

from core.database import Base

# helper functions
def uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

def now_col() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

# -- user models --
class RoleEnum(str, enum.Enum):
    ADMIN = "admin"
    USER = "user"

class Users(Base):
    __tablename__ = "users"

    id:                 Mapped[uuid.UUID]       = uuid_pk()

    handle:             Mapped[str]             = mapped_column(CITEXT, unique=True, nullable=False)
    email:              Mapped[str]             = mapped_column(CITEXT, unique=True, nullable=False)
    role:               Mapped[RoleEnum]        = mapped_column(
                                                    Enum(RoleEnum, name="user_role_enum", native_enum=True, values_callable=lambda obj: [e.value for e in obj]),
                                                    default=RoleEnum.USER, server_default=RoleEnum.USER.value, nullable=False
                                                )
    password_hashed:    Mapped[str]             = mapped_column(Text, nullable=False)


# -- media models --
class GenreEnum(str, enum.Enum):
    ANIME = "anime"
    DRAMA = "drama"
    ACTION = "action"
    COMEDY = "comedy"
    SCI_FI = "sci-fi"

# The Association Table (Junction Table)
show_tags = Table(
    "show_tags",
    Base.metadata,
    Column("show_id", ForeignKey("shows.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)

# The Tags Model
class Tags(Base):
    __tablename__ = "tags"

    id:     Mapped[uuid.UUID]     = uuid_pk()
    name:   Mapped[str]           = mapped_column(String(50), unique=True, nullable=False)

    shows:  Mapped[list["Shows"]] = relationship("Shows", secondary=show_tags, back_populates="tags")


class Shows(Base):
    __tablename__ = "shows"

    id:                 Mapped[uuid.UUID]       = uuid_pk()
    title:              Mapped[str]             = mapped_column(String(255), nullable=False)
    description:        Mapped[str]             = mapped_column(Text, nullable=False, server_default="No description provided")
    genre:              Mapped[GenreEnum]       = mapped_column(Enum(GenreEnum, name="genre_enum", native_enum=True, values_callable=lambda obj: [e.value for e in obj]), default=GenreEnum.DRAMA, server_default=GenreEnum.DRAMA.value, nullable=False)
    thumbnail_url:      Mapped[str]             = mapped_column(Text, nullable=True)
    created_at:         Mapped[datetime]        = now_col()

    # Relationship: one show got many seasons. this is a seperate database linked into this one
    tags:               Mapped[list["Tags"]]    = relationship("Tags", secondary=show_tags, back_populates="shows", lazy="selectin")
    seasons:            Mapped[list["Seasons"]] = relationship("Seasons", back_populates="show", cascade="all, delete-orphan")

class Seasons(Base):
    __tablename__ = "seasons"

    id:                 Mapped[uuid.UUID]       = uuid_pk()
    show_id:            Mapped[uuid.UUID]       = mapped_column(ForeignKey("shows.id", ondelete="CASCADE"), nullable=False)
    season_number:      Mapped[int]             = mapped_column(Integer, nullable=False)
    created_at:         Mapped[datetime]        = now_col()

    show:               Mapped["Shows"]         = relationship("Shows", back_populates="seasons")
    episodes:           Mapped[list["Episode"]] = relationship("Episode", back_populates="season", cascade="all, delete-orphan")

class Episode(Base):
    __tablename__ = "episodes"

    id:                 Mapped[uuid.UUID]       = uuid_pk()
    season_id:          Mapped[uuid.UUID]       = mapped_column(ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False)
    episode_number:     Mapped[int]             = mapped_column(Integer, nullable=False)
    title:              Mapped[str]             = mapped_column(String(255), nullable=False)
    description:        Mapped[str]             = mapped_column(Text, nullable=True)
    video_url:          Mapped[str]             = mapped_column(Text, nullable=False) 
    duration_secs:      Mapped[int]             = mapped_column(Integer, nullable=True)
    created_at:         Mapped[datetime]        = now_col()

    season:             Mapped["Seasons"]       = relationship("Seasons", back_populates="episodes")