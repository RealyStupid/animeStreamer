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


# --- Shows and media ---
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

class ShowResponse(BaseModel):
    id: uuid.UUID
    title: str
    description: str
    genre: GenreEnum
    thumbnail_url: str | None = None
    tags: list[TagResponse] = Field(default_factory=list)

    class Config:
        from_attributes = True