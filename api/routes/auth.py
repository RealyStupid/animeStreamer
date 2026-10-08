"""
    API router for authentication such as signing in and registering
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from schemas import UserResponse, UserRegister, Token

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

@auth.post("/token", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    stmt = select(Users).where(or_(Users.email == form_data.username, Users.handle == form_data.username))
    user = (await db.execute(stmt)).scalar_one_or_none()

    if not user or not verify_password(form_data.password, user.password_hashed):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(data={"sub": user.email})
    return {"access_token": access_token, "token_type": "bearer"}