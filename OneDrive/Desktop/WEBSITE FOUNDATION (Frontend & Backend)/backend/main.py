from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import List
import models
import schemas
from database import SessionLocal, engine
from auth import get_current_user, create_access_token
from datetime import datetime, timedelta
from email_handler import router as email_router
import openai
from pydantic import BaseModel
import os
from dotenv import load_dotenv
from .database import Base
from .auth import router as auth_router
from .properties import router as properties_router
from .ticket_system import router as ticket_router
from .qube_integration import router as qube_router

load_dotenv()

# Initialize OpenAI
openai.api_key = os.getenv("OPENAI_API_KEY")

# Create database tables
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Property Management API")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(email_router)
app.include_router(auth_router, prefix="/api", tags=["Authentication"])
app.include_router(properties_router, prefix="/api", tags=["Properties"])
app.include_router(ticket_router, prefix="/api", tags=["Support Tickets"])
app.include_router(qube_router, prefix="/api", tags=["Qube Integration"])

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Authentication routes
@app.post("/register", response_model=schemas.User)
def register_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(models.User.email == user.email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    new_user = models.User(
        email=user.email,
        hashed_password=schemas.get_password_hash(user.password),
        full_name=user.full_name,
        role=user.role
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

@app.post("/login")
def login(user_credentials: schemas.UserLogin, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == user_credentials.email).first()
    if not user or not schemas.verify_password(user_credentials.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token = create_access_token(data={"sub": user.email})
    return {"access_token": access_token, "token_type": "bearer"}

# Property routes
@app.get("/properties", response_model=List[schemas.Property])
def get_properties(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    properties = db.query(models.Property).offset(skip).limit(limit).all()
    return properties

@app.post("/properties", response_model=schemas.Property)
def create_property(
    property: schemas.PropertyCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized to create properties")
    
    db_property = models.Property(**property.dict())
    db.add(db_property)
    db.commit()
    db.refresh(db_property)
    return db_property

# Maintenance ticket routes
@app.post("/tickets", response_model=schemas.MaintenanceTicket)
def create_ticket(
    ticket: schemas.MaintenanceTicketCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    db_ticket = models.MaintenanceTicket(
        **ticket.dict(),
        user_id=current_user.id,
        status="pending"
    )
    db.add(db_ticket)
    db.commit()
    db.refresh(db_ticket)
    return db_ticket

@app.get("/tickets", response_model=List[schemas.MaintenanceTicket])
def get_tickets(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    if current_user.role == "admin":
        tickets = db.query(models.MaintenanceTicket).all()
    else:
        tickets = db.query(models.MaintenanceTicket).filter(
            models.MaintenanceTicket.user_id == current_user.id
        ).all()
    return tickets

# Admin dashboard statistics
@app.get("/admin/stats")
def get_admin_stats(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized to access admin stats")
    
    total_properties = db.query(models.Property).count()
    total_tenants = db.query(models.User).filter(models.User.role == "tenant").count()
    pending_tickets = db.query(models.MaintenanceTicket).filter(
        models.MaintenanceTicket.status == "pending"
    ).count()
    
    return {
        "total_properties": total_properties,
        "total_tenants": total_tenants,
        "pending_tickets": pending_tickets
    }

class ChatRequest(BaseModel):
    message: str

@app.post("/api/chat")
async def chat(request: ChatRequest):
    try:
        # Prepare the prompt for the chatbot
        prompt = f"""You are a helpful property management assistant. 
        Answer the following question about property management, maintenance, or tenant services: {request.message}
        Keep the response concise and informative."""

        # Call OpenAI API
        response = await openai.ChatCompletion.acreate(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are a helpful property management assistant."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=150
        )

        return {"response": response.choices[0].message.content}

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error processing chat request: {str(e)}"
        )

@app.get("/")
async def root():
    return {"message": "Welcome to the Property Management API"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000) 