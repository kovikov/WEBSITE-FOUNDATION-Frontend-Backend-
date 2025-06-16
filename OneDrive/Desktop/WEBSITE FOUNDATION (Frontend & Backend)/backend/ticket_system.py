from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import openai
from .database import get_db
from sqlalchemy.orm import Session
from .models import Ticket, User
from .auth import get_current_user
import os
from dotenv import load_dotenv
import chromadb
from chromadb.config import Settings
import json

load_dotenv()

router = APIRouter()

# Initialize ChromaDB
chroma_client = chromadb.Client(Settings(
    chroma_db_impl="duckdb+parquet",
    persist_directory="data/chroma"
))

# Create or get collection
collection = chroma_client.get_or_create_collection(
    name="property_policies",
    metadata={"hnsw:space": "cosine"}
)

class TicketCreate(BaseModel):
    title: str
    description: str
    category: str
    priority: str

class TicketResponse(BaseModel):
    id: str
    title: str
    description: str
    status: str
    priority: str
    category: str
    created_at: datetime
    updated_at: datetime
    ai_response: Optional[str] = None
    staff_response: Optional[str] = None

def load_policy_documents():
    """Load policy documents into ChromaDB."""
    policy_dir = "data/policies"
    if not os.path.exists(policy_dir):
        os.makedirs(policy_dir)
        # Create sample policy documents
        sample_policies = {
            "maintenance.txt": "Maintenance requests should be submitted through the portal. Emergency maintenance is available 24/7.",
            "billing.txt": "Rent is due on the 1st of each month. Late fees apply after the 5th.",
            "noise.txt": "Quiet hours are from 10 PM to 7 AM. Excessive noise complaints may result in lease violations.",
            "security.txt": "All visitors must be registered at the front desk. Security cameras are in operation 24/7.",
            "general.txt": "Office hours are Monday-Friday 9 AM to 5 PM. Emergency contact available after hours."
        }
        for filename, content in sample_policies.items():
            with open(os.path.join(policy_dir, filename), "w") as f:
                f.write(content)

    # Load documents into ChromaDB
    for filename in os.listdir(policy_dir):
        with open(os.path.join(policy_dir, filename), "r") as f:
            content = f.read()
            collection.add(
                documents=[content],
                metadatas=[{"source": filename}],
                ids=[filename]
            )

def generate_ai_response(ticket: Ticket, db: Session) -> str:
    """Generate AI response based on ticket content and policy documents."""
    try:
        # Search relevant policy documents
        results = collection.query(
            query_texts=[ticket.description],
            n_results=3
        )

        # Get user's ticket history
        user_tickets = db.query(Ticket).filter(
            Ticket.user_id == ticket.user_id
        ).order_by(Ticket.created_at.desc()).limit(5).all()

        # Prepare context for AI
        context = f"""
        Ticket Category: {ticket.category}
        Priority: {ticket.priority}
        
        Relevant Policies:
        {json.dumps(results['documents'][0], indent=2)}
        
        User's Recent Tickets:
        {json.dumps([{'title': t.title, 'status': t.status} for t in user_tickets], indent=2)}
        """

        # Generate response using OpenAI
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {
                    "role": "system",
                    "content": """You are a helpful property management assistant.
                    Generate a response based on the provided policies and user history.
                    Be professional, empathetic, and solution-oriented."""
                },
                {
                    "role": "user",
                    "content": f"Context: {context}\n\nTicket: {ticket.description}\n\nGenerate an appropriate response:"
                }
            ],
            temperature=0.7,
            max_tokens=200
        )

        return response.choices[0].message.content

    except Exception as e:
        print(f"Error generating AI response: {str(e)}")
        return "Thank you for your ticket. Our team will review it shortly."

@router.post("/api/tickets", response_model=TicketResponse)
async def create_ticket(
    ticket: TicketCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new support ticket."""
    try:
        # Create ticket
        db_ticket = Ticket(
            title=ticket.title,
            description=ticket.description,
            category=ticket.category,
            priority=ticket.priority,
            status="open",
            user_id=current_user.id
        )
        db.add(db_ticket)
        db.commit()
        db.refresh(db_ticket)

        # Generate AI response
        ai_response = generate_ai_response(db_ticket, db)
        db_ticket.ai_response = ai_response
        db.commit()

        return db_ticket

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/tickets", response_model=List[TicketResponse])
async def get_tickets(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all tickets for the current user."""
    try:
        tickets = db.query(Ticket).filter(
            Ticket.user_id == current_user.id
        ).order_by(Ticket.created_at.desc()).all()
        return tickets
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/tickets/{ticket_id}", response_model=TicketResponse)
async def get_ticket(
    ticket_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a specific ticket."""
    try:
        ticket = db.query(Ticket).filter(
            Ticket.id == ticket_id,
            Ticket.user_id == current_user.id
        ).first()
        if not ticket:
            raise HTTPException(status_code=404, detail="Ticket not found")
        return ticket
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Initialize policy documents
load_policy_documents() 