"""
    Routes for user to get data OR other suff
"""
from fastapi import APIRouter, Depends

from schemas import UserResponse
from models import Users
from core.security import get_current_user

users = APIRouter(prefix="/users", tags=["Users"])

@users.get("/me", response_model=UserResponse)
async def read_user_me(current_user: Users = Depends(get_current_user)):
    return current_user