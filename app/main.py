from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import engine, Base
from app.init_admin import create_admin

from app.api import auth, generation as generation_api, notes as notes_api

# Import the __init__.py to set up relationships
from app.models import *

# Create database tables
Base.metadata.create_all(bind=engine)

# Create admin user
create_admin()

app = FastAPI(
    title="Notes Generation API",
    description="AI-powered educational notes generation system",
    version="1.0.0"
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

@app.get("/")
async def root():
    return {"message": "Notes Generation API is running"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}