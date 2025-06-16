from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, EmailStr
from typing import Optional
import openai
from .email_classifier import EmailClassifier, EmailCategory
import os
from dotenv import load_dotenv
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

load_dotenv()

router = APIRouter()

class EmailRequest(BaseModel):
    sender_email: EmailStr
    subject: str
    content: str
    property_id: Optional[str] = None

class EmailResponse(BaseModel):
    response: str
    category: EmailCategory
    escalated: bool

async def generate_email_response(
    email_content: str,
    category: EmailCategory,
    property_id: Optional[str] = None
) -> str:
    try:
        # Prepare context for the AI
        context = f"""
        Category: {category.category}
        Department: {category.department}
        Priority: {category.priority}
        Property ID: {property_id if property_id else 'Not specified'}
        """

        # Call OpenAI API for response generation
        response = await openai.ChatCompletion.acreate(
            model="gpt-4",
            messages=[
                {
                    "role": "system",
                    "content": """You are a professional property management assistant.
                    Generate a polite, helpful, and contextually appropriate email response.
                    Keep the response concise but informative."""
                },
                {
                    "role": "user",
                    "content": f"Context: {context}\n\nOriginal email: {email_content}\n\nGenerate an appropriate response:"
                }
            ],
            temperature=0.7,
            max_tokens=200
        )

        return response.choices[0].message.content

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error generating email response: {str(e)}"
        )

def send_email(
    to_email: str,
    subject: str,
    content: str,
    from_email: str = os.getenv("SMTP_FROM_EMAIL", "noreply@propertypro.com")
) -> None:
    try:
        msg = MIMEMultipart()
        msg["From"] = from_email
        msg["To"] = to_email
        msg["Subject"] = subject

        msg.attach(MIMEText(content, "plain"))

        # Configure SMTP settings
        smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
        smtp_port = int(os.getenv("SMTP_PORT", "587"))
        smtp_username = os.getenv("SMTP_USERNAME")
        smtp_password = os.getenv("SMTP_PASSWORD")

        # Send email
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(smtp_username, smtp_password)
            server.send_message(msg)

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error sending email: {str(e)}"
        )

@router.post("/api/email/respond", response_model=EmailResponse)
async def handle_email(request: EmailRequest):
    try:
        # Classify the email
        category = await EmailClassifier.classify_email(request.content)

        # Generate response
        response = await generate_email_response(
            request.content,
            category,
            request.property_id
        )

        # Check if escalation is needed
        should_escalate = EmailClassifier.should_escalate(category)

        if should_escalate:
            # Send to appropriate department
            department_email = EmailClassifier.get_department_email(category.category)
            send_email(
                department_email,
                f"Escalated: {request.subject}",
                f"""
                Original email from: {request.sender_email}
                Category: {category.category}
                Priority: {category.priority}
                Content: {request.content}
                """
            )

        # Send response to the original sender
        send_email(
            request.sender_email,
            f"Re: {request.subject}",
            response
        )

        return EmailResponse(
            response=response,
            category=category,
            escalated=should_escalate
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error processing email: {str(e)}"
        ) 