"""
    Pydantic request bodies and response models.
"""
import uuid
from pydantic import BaseModel, EmailStr, Field
from models import RoleEnum, GenreEnum

# --- Auth and sign in ---
class UserRegister(BaseModel):
    handle: str = Field(min_length=3, max_length=30, pattern=r"^[a-zA-Z0-9_\-]+$")
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    id: uuid.UUID
    handle: str
    email: EmailStr
    role: RoleEnum

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str


# --- Media ---
# shows
class ShowCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(default="No description provided")
    genre: GenreEnum = GenreEnum.DRAMA
    tags: list[str] = Field(default_factory=list)

class TagResponse(BaseModel):
    id: uuid.UUID
    name: str

    class Config:
        from_attributes = True

class CreatorResponse(BaseModel):
    id: uuid.UUID
    handle: str

    class Config:
        from_attributes = True

class ShowResponse(BaseModel):
    id: uuid.UUID
    title: str
    description: str
    genre: GenreEnum
    thumbnail_url: str | None = None
    is_private: bool = False
    created_by: CreatorResponse | None = None
    tags: list[TagResponse] = Field(default_factory=list)

    class Config:
        from_attributes = True

# seasons
class SeasonCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str = Field(default="No description provided")

class SeasonUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None

class SeasonResponse(BaseModel):
    id: uuid.UUID
    show_id: uuid.UUID
    season_number: int
    name: str
    description: str
    thumbnail_url: str | None = None
    created_by: CreatorResponse | None = None

    class Config:
        from_attributes = True

# episodes
class EpisodeResponse(BaseModel):
    id: uuid.UUID
    season_id: uuid.UUID
    episode_number: int
    title: str
    description: str | None = None
    video_url: str
    duration_secs: int | None = None
    created_by: CreatorResponse | None = None

    class Config:
        from_attributes = True

class EpisodePlaybackResponse(BaseModel):
    playback_url: str