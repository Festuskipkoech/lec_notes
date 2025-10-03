from datetime import timedelta, datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.dependencies.dependencies import get_current_user
from app.schemas.auth import (
    UserCreate, UserLogin, Token, TokenRefresh, User,
    ForgotPasswordRequest, ResetPasswordRequest,
    VerifyEmailResponse, ResetPasswordResponse
)
from app.services.auth_service import auth_service
from app.models.user import User as UserModel
from app.config import settings
from app.utils.email import EmailService
import uuid

router = APIRouter(prefix="/auth", tags=["authentication"])
email_service = EmailService()

@router.post("/register", response_model=User)
async def register_user(user_data: UserCreate, db: Session = Depends(get_db)):
    existing_user = auth_service.get_user_by_email(db, user_data.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    hashed_password = auth_service.get_password_hash(user_data.password)
    verification_token = str(uuid.uuid4())
    expires = datetime.utcnow() + timedelta(hours=24)

    db_user = UserModel(
        email=user_data.email,
        password_hash=hashed_password,
        full_name=user_data.full_name,
        phone=user_data.phone,
        role=user_data.role,
        verification_token=verification_token,
        verification_token_expires=expires
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    
    # Send email verification
    await email_service.send_verification_email_secure_async(
        db_user.email, verification_token, verification_token
    )
    
    return db_user

@router.get("/verify/{token}", response_model=VerifyEmailResponse)
async def verify_email(token: str, db: Session = Depends(get_db)):
    user = db.query(UserModel).filter(UserModel.verification_token == token).first()
    if not user or user.verification_token_expires < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Invalid or expired verification link")

    user.is_verified = True
    user.verification_token = None
    user.verification_token_expires = None
    db.commit()

    return {"message": "Email successfully verified"}

@router.post("/login", response_model=Token)
async def login_user(login_data: UserLogin, db: Session = Depends(get_db)):
    user = auth_service.authenticate_user(db, login_data.email, login_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Please verify your email before logging in"
        )
    
    access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
    access_token = auth_service.create_access_token(
        data={"sub": user.email}, expires_delta=access_token_expires
    )
    
    refresh_token = auth_service.create_refresh_token()
    auth_service.update_refresh_token(db, user, refresh_token)
    
    return {
        "access_token": access_token, 
        "refresh_token": refresh_token,
        "token_type": "bearer"
    }

@router.post("/refresh", response_model=Token)
async def refresh_token(token_data: TokenRefresh, db: Session = Depends(get_db)):
    user = auth_service.verify_refresh_token(db, token_data.refresh_token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    
    access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
    access_token = auth_service.create_access_token(
        data={"sub": user.email}, expires_delta=access_token_expires
    )
    
    new_refresh_token = auth_service.create_refresh_token()
    auth_service.update_refresh_token(db, user, new_refresh_token)
    
    return {
        "access_token": access_token,
        "refresh_token": new_refresh_token,
        "token_type": "bearer"
    }

@router.post("/logout")
async def logout_user(
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    auth_service.revoke_refresh_token(db, current_user)
    return {"message": "Successfully logged out"}

@router.get("/me", response_model=User)
async def get_current_user_info(current_user: UserModel = Depends(get_current_user)):
    return current_user

@router.post("/forgot-password")
async def forgot_password(request: ForgotPasswordRequest, db: Session = Depends(get_db)):
    user = db.query(UserModel).filter(UserModel.email == request.email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    reset_token = str(uuid.uuid4())
    expires = datetime.utcnow() + timedelta(hours=1)

    user.reset_token = reset_token
    user.reset_token_expires = expires
    db.commit()

    await email_service.send_password_reset_email_secure_async(
        user.email, reset_token, reset_token
    )

    return {"message": "Password reset email sent"}

@router.post("/reset-password", response_model=ResetPasswordResponse)
async def reset_password(data: ResetPasswordRequest, db: Session = Depends(get_db)):
    user = db.query(UserModel).filter(UserModel.reset_token == data.token).first()
    if not user or user.reset_token_expires < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    user.password_hash = auth_service.get_password_hash(data.new_password)
    user.reset_token = None
    user.reset_token_expires = None
    db.commit()

    return {"message": "Password successfully reset"}
