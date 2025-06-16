from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
from typing import List, Optional, Dict
import httpx
import jwt
from datetime import datetime, timedelta
from .database import get_db
from sqlalchemy.orm import Session
from .models import Ticket, User, Property
from .auth import get_current_user
import os
from dotenv import load_dotenv
import json

load_dotenv()

router = APIRouter()

# Qube API Configuration
QUBE_API_URL = os.getenv("QUBE_API_URL", "https://api.qube.com/v1")
QUBE_CLIENT_ID = os.getenv("QUBE_CLIENT_ID")
QUBE_CLIENT_SECRET = os.getenv("QUBE_CLIENT_SECRET")
QUBE_WEBHOOK_SECRET = os.getenv("QUBE_WEBHOOK_SECRET")

class QubeCase(BaseModel):
    case_id: str
    title: str
    description: str
    status: str
    priority: str
    category: str
    tenant_id: str
    property_id: str
    created_at: datetime
    updated_at: datetime
    qube_comments: List[Dict] = []

class QubeComment(BaseModel):
    comment_id: str
    case_id: str
    content: str
    author: str
    created_at: datetime

class BulkUpdateRequest(BaseModel):
    case_ids: List[str]
    status: Optional[str] = None
    priority: Optional[str] = None

async def get_qube_token() -> str:
    """Get Qube API authentication token."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{QUBE_API_URL}/auth/token",
                json={
                    "client_id": QUBE_CLIENT_ID,
                    "client_secret": QUBE_CLIENT_SECRET,
                    "grant_type": "client_credentials"
                }
            )
            response.raise_for_status()
            return response.json()["access_token"]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get Qube token: {str(e)}")

async def sync_ticket_to_qube(ticket: Ticket, db: Session) -> str:
    """Create or update a case in Qube."""
    try:
        token = await get_qube_token()
        
        # Prepare case data
        case_data = {
            "title": ticket.title,
            "description": ticket.description,
            "status": ticket.status,
            "priority": ticket.priority,
            "category": ticket.category,
            "tenant_id": ticket.user_id,
            "property_id": ticket.property_id if hasattr(ticket, 'property_id') else None,
            "metadata": {
                "internal_ticket_id": ticket.id,
                "created_at": ticket.created_at.isoformat(),
                "updated_at": ticket.updated_at.isoformat() if ticket.updated_at else None
            }
        }

        async with httpx.AsyncClient() as client:
            # Check if case already exists in Qube
            if hasattr(ticket, 'qube_case_id') and ticket.qube_case_id:
                response = await client.put(
                    f"{QUBE_API_URL}/cases/{ticket.qube_case_id}",
                    headers={"Authorization": f"Bearer {token}"},
                    json=case_data
                )
            else:
                response = await client.post(
                    f"{QUBE_API_URL}/cases",
                    headers={"Authorization": f"Bearer {token}"},
                    json=case_data
                )
            
            response.raise_for_status()
            case_id = response.json()["case_id"]
            
            # Update ticket with Qube case ID
            ticket.qube_case_id = case_id
            db.commit()
            
            return case_id
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to sync ticket with Qube: {str(e)}")

@router.post("/api/qube/cases/bulk-update")
async def bulk_update_cases(
    request: BulkUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Bulk update multiple Qube cases."""
    try:
        token = await get_qube_token()
        
        # Get all tickets that need to be updated
        tickets = db.query(Ticket).filter(
            Ticket.qube_case_id.in_(request.case_ids)
        ).all()
        
        # Update each ticket and sync with Qube
        for ticket in tickets:
            if request.status:
                ticket.status = request.status
            if request.priority:
                ticket.priority = request.priority
            
            # Sync with Qube
            await sync_ticket_to_qube(ticket, db)
        
        db.commit()
        return {"message": "Bulk update successful", "updated_count": len(tickets)}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/qube/webhook")
async def qube_webhook(request: Request):
    """Handle webhooks from Qube for case updates."""
    try:
        # Verify webhook signature
        signature = request.headers.get("X-Qube-Signature")
        if not signature:
            raise HTTPException(status_code=401, detail="Missing signature")
        
        payload = await request.json()
        
        # Verify signature
        expected_signature = jwt.encode(
            payload,
            QUBE_WEBHOOK_SECRET,
            algorithm="HS256"
        )
        if signature != expected_signature:
            raise HTTPException(status_code=401, detail="Invalid signature")
        
        # Process webhook
        event_type = payload.get("event_type")
        case_data = payload.get("case")
        
        if event_type == "case.updated":
            # Update local ticket
            db = next(get_db())
            ticket = db.query(Ticket).filter(
                Ticket.qube_case_id == case_data["case_id"]
            ).first()
            
            if ticket:
                ticket.status = case_data["status"]
                ticket.updated_at = datetime.utcnow()
                db.commit()
        
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/qube/cases", response_model=List[QubeCase])
async def get_qube_cases(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all Qube cases for the current user's properties."""
    try:
        token = await get_qube_token()
        
        # Get user's properties
        properties = db.query(Property).filter(
            Property.owner_id == current_user.id
        ).all()
        property_ids = [p.id for p in properties]
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{QUBE_API_URL}/cases",
                headers={"Authorization": f"Bearer {token}"},
                params={"property_ids": property_ids}
            )
            response.raise_for_status()
            return response.json()["cases"]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/qube/cases/{case_id}/comments")
async def add_qube_comment(
    case_id: str,
    comment: QubeComment,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Add a comment to a Qube case."""
    try:
        token = await get_qube_token()
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{QUBE_API_URL}/cases/{case_id}/comments",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "content": comment.content,
                    "author": current_user.full_name
                }
            )
            response.raise_for_status()
            return response.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/qube/cases/{case_id}", response_model=QubeCase)
async def get_qube_case(
    case_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a specific Qube case."""
    try:
        token = await get_qube_token()
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{QUBE_API_URL}/cases/{case_id}",
                headers={"Authorization": f"Bearer {token}"}
            )
            response.raise_for_status()
            return response.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) 