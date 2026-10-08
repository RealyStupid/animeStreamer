"""
    Pydantic request bodies and response models.
"""
import uuid
from pydantic import BaseModel, EmailStr, Field
from models import RoleEnum

# Auth and sign in
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