from app.database import SessionLocal
from app.models.user import User, UserRole
from app.services.auth_service import auth_service
from app.config import settings

def create_admin():
    """Create admin user if doesn't exist"""
    db = SessionLocal()
    
    admin_email = settings.admin_email
    admin_password = settings.admin_password
    
    # Check if admin exists
    existing_admin = db.query(User).filter(User.email == admin_email).first()
    if existing_admin:
        db.close()
        return
    
    # Create admin
    hashed_password = auth_service.get_password_hash(admin_password)
    admin = User(
        email=admin_email,
        password_hash=hashed_password,
        role=UserRole.admin,
        full_name="Admin User"
    )
    
    db.add(admin)
    db.commit()
    db.close()
    print(f"Admin created: {admin_email}")