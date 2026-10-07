"""
    API router for authentication such as signing in and registering
"""

from fastapi import APIRouter, Depends, HTTPException

from schemas import UserResponse, UserRegister

from core.security import hash_password, verify_password, create_access_token, get_current_user

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from core.database import get_db
from models import Users


auth = APIRouter(prefix="/auth", tags=["Authentication"])

@auth.post("/register", response_model=UserResponse)
async def register(user_data: UserRegister, db: AsyncSession = Depends(get_db)):
    stmt = select(Users).where(or_(Users.email == user_data.email, Users.handle == user_data.handle))
    existing = (await db.execute(stmt)).scalar_one_or_none()

    if existing:
        raise HTTPException(status_code=400, detail="Email or Handle aleady exist.")

    new_user = Users(
        handle=user_data.handle, 
        email=user_data.email, 
        password_hashed=hash_password(user_data.password)
    )

    db.add(new_user)

    await db.commit()
    await db.refresh(new_user)
    return new_user