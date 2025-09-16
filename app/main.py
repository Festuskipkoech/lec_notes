from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import engine, Base
from app.init_admin import create_admin

# Import existing API routes
from app.api import auth, generation as generation_api, notes as notes_api

# Import new assessment API  
from app.api import assessments as assessment_api

# Import models explicitly to avoid import errors
try:
    from app.models.user import User
    from app.models.notes import Topic, Subtopic
    from app.models.generation import GenerationSession
    from app.models.content_chunks import ContentChunk
    from app.models.assessments import (
        SubtopicAssessment, Assignment, AssignmentSubmission, 
        PracticeQuiz
    )
    print("All models imported successfully")
except ImportError as e:
    print(f"Model import error: {e}")

# Enable pgvector extension
def enable_pgvector():
    try:
        import psycopg2
        from app.config import settings
        
        conn = psycopg2.connect(settings.database_url)
        conn.autocommit = True
        cursor = conn.cursor()
        
        cursor.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        cursor.close()
        conn.close()
        print("pgvector extension enabled")
        return True
    except Exception as e:
        print(f"pgvector error: {e}")
        return False

# Add missing columns to users table
def add_user_columns():
    try:
        import psycopg2
        from app.config import settings
        
        conn = psycopg2.connect(settings.database_url)
        conn.autocommit = True
        cursor = conn.cursor()
        
        # Check if columns exist
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'users' AND column_name IN ('full_name', 'phone', 'refresh_token')
        """)
        existing_columns = [row[0] for row in cursor.fetchall()]
        
        columns_to_add = []
        if 'full_name' not in existing_columns:
            columns_to_add.append("ADD COLUMN full_name VARCHAR NOT NULL DEFAULT ''")
        if 'phone' not in existing_columns:
            columns_to_add.append("ADD COLUMN phone VARCHAR")
        if 'refresh_token' not in existing_columns:
            columns_to_add.append("ADD COLUMN refresh_token VARCHAR")
        
        if columns_to_add:
            alter_query = f"ALTER TABLE users {', '.join(columns_to_add)}"
            cursor.execute(alter_query)
            print(f"Added columns to users table: {[col.split()[2] for col in columns_to_add]}")
        else:
            print("All user columns already exist")
        
        cursor.close()
        conn.close()
        return True
    except Exception as e:
        print(f"Error adding user columns: {e}")
        return False

# Add assessment columns
def add_assessment_columns():
    try:
        import psycopg2
        from app.config import settings
        
        conn = psycopg2.connect(settings.database_url)
        conn.autocommit = True
        cursor = conn.cursor()
        
        # Check for both ai_grades and status columns
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'assignment_submissions' AND column_name IN ('ai_grades', 'status')
        """)
        existing_columns = [row[0] for row in cursor.fetchall()]
        
        columns_to_add = []
        if 'ai_grades' not in existing_columns:
            columns_to_add.append("ADD COLUMN ai_grades JSON")
        if 'status' not in existing_columns:
            columns_to_add.append("ADD COLUMN status VARCHAR(50) DEFAULT 'submitted'")
        
        if columns_to_add:
            alter_query = f"ALTER TABLE assignment_submissions {', '.join(columns_to_add)}"
            cursor.execute(alter_query)
            print(f"Added columns to assignment_submissions: {[col.split()[2] for col in columns_to_add]}")
        else:
            print("All assessment columns already exist")
        
        cursor.close()
        conn.close()
        return True
    except Exception as e:
        print(f"Error adding assessment columns: {e}")
        return False

# Only run these during startup, not import
def startup_tasks():
    enable_pgvector()
    # Create database tables
    Base.metadata.create_all(bind=engine)
    # Add missing user columns
    add_user_columns()
    # Add missing assessment columns
    add_assessment_columns()  # <-- THIS ADDS BOTH ai_grades AND status COLUMNS
    # Create admin user
    create_admin()

app = FastAPI(
    title="Notes Generation API with Clean Assessment System",
    description="AI-powered educational notes with integrated quiz generation",
    version="2.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router)
app.include_router(generation_api.router)
app.include_router(notes_api.router)
app.include_router(assessment_api.router)

@app.on_event("startup")
async def startup_event():
    startup_tasks()

@app.get("/")
async def root():
    return {
        "message": "Clean Notes Generation API with Assessment System",
        "features": [
            "Auto-generated subtopic quizzes (content + quiz together)",
            "Admin assignment creation and grading", 
            "Student practice quiz generation",
            "Clean, minimal codebase"
        ]
    }

@app.get("/health")
async def health_check():
    return {"status": "healthy", "assessment_system": "clean and minimal"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)