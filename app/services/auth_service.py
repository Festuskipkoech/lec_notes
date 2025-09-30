from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from app.models.user import User
from app.schemas.auth import TokenData
from app.config import settings
import secrets

pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=12
)

class AuthService:
    
    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        try:
            # Ensure hashed_password is a string, not bytes
            if isinstance(hashed_password, bytes):
                hashed_password = hashed_password.decode('utf-8')
            
            # Ensure plain_password is a string
            if isinstance(plain_password, bytes):
                plain_password = plain_password.decode('utf-8')
                
            return pwd_context.verify(plain_password, hashed_password)
        except Exception as e:
            print(f"Password verification error: {e}")
            return False
    
    @staticmethod
    def get_password_hash(password: str) -> str:
        # Ensure password is a string
        if isinstance(password, bytes):
            password = password.decode('utf-8')
            
        hashed = pwd_context.hash(password)
        
        # Ensure it returns a string, not bytes
        if isinstance(hashed, bytes):
            return hashed.decode('utf-8')
        return hashed
    
    @staticmethod
    def authenticate_user(db: Session, email: str, password: str) -> Optional[User]:
        user = db.query(User).filter(User.email == email).first()
        if not user or not AuthService.verify_password(password, user.password_hash):
            return None
        return user
    
    @staticmethod
    def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=15)
        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)
        return encoded_jwt
    
    @staticmethod
    def create_refresh_token() -> str:
        return secrets.token_urlsafe(32)
    
    @staticmethod
    def verify_token(token: str, credentials_exception) -> TokenData:
        try:
            payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
            email: str = payload.get("sub")
            if email is None:
                raise credentials_exception
            token_data = TokenData(email=email)
        except JWTError:
            raise credentials_exception
        return token_data
    
    @staticmethod
    def verify_refresh_token(db: Session, refresh_token: str) -> Optional[User]:
        user = db.query(User).filter(User.refresh_token == refresh_token).first()
        return user if user and user.is_active else None
    
    @staticmethod
    def update_refresh_token(db: Session, user: User, refresh_token: str):
        user.refresh_token = refresh_token
        db.commit()
    
    @staticmethod
    def revoke_refresh_token(db: Session, user: User):
        user.refresh_token = None
        db.commit()
    
    @staticmethod
    def get_user_by_email(db: Session, email: str) -> Optional[User]:
        return db.query(User).filter(User.email == email).first()

auth_service = AuthService()