from fastapi import BackgroundTasks
from typing import List, Optional
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
from dotenv import load_dotenv
from .database import get_db
from .models import User, Ticket
from sqlalchemy.orm import Session

load_dotenv()

# Email Configuration
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
EMAIL_FROM = os.getenv("EMAIL_FROM", "noreply@propertymanagement.com")

def send_email(to_email: str, subject: str, html_content: str):
    """Send an email using SMTP."""
    try:
        msg = MIMEMultipart()
        msg["From"] = EMAIL_FROM
        msg["To"] = to_email
        msg["Subject"] = subject

        msg.attach(MIMEText(html_content, "html"))

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.send_message(msg)
    except Exception as e:
        print(f"Failed to send email: {str(e)}")

def notify_case_created(background_tasks: BackgroundTasks, ticket: Ticket, db: Session):
    """Send notification when a new case is created."""
    # Get tenant email
    tenant = db.query(User).filter(User.id == ticket.user_id).first()
    if not tenant:
        return

    # Get property owner email
    property_owner = db.query(User).filter(
        User.id == ticket.property.owner_id
    ).first()
    if not property_owner:
        return

    # Prepare email content
    subject = f"New Support Case Created: {ticket.title}"
    html_content = f"""
    <html>
        <body>
            <h2>New Support Case Created</h2>
            <p><strong>Case ID:</strong> {ticket.id}</p>
            <p><strong>Title:</strong> {ticket.title}</p>
            <p><strong>Description:</strong> {ticket.description}</p>
            <p><strong>Priority:</strong> {ticket.priority}</p>
            <p><strong>Category:</strong> {ticket.category}</p>
            <p>You can view and respond to this case in your dashboard.</p>
        </body>
    </html>
    """

    # Send emails in background
    background_tasks.add_task(send_email, tenant.email, subject, html_content)
    background_tasks.add_task(send_email, property_owner.email, subject, html_content)

def notify_case_updated(
    background_tasks: BackgroundTasks,
    ticket: Ticket,
    db: Session,
    update_type: str,
    comment: Optional[str] = None
):
    """Send notification when a case is updated."""
    # Get tenant email
    tenant = db.query(User).filter(User.id == ticket.user_id).first()
    if not tenant:
        return

    # Get property owner email
    property_owner = db.query(User).filter(
        User.id == ticket.property.owner_id
    ).first()
    if not property_owner:
        return

    # Prepare email content
    subject = f"Case Updated: {ticket.title}"
    html_content = f"""
    <html>
        <body>
            <h2>Case Update Notification</h2>
            <p><strong>Case ID:</strong> {ticket.id}</p>
            <p><strong>Title:</strong> {ticket.title}</p>
            <p><strong>Update Type:</strong> {update_type}</p>
            <p><strong>New Status:</strong> {ticket.status}</p>
            <p><strong>New Priority:</strong> {ticket.priority}</p>
            {f'<p><strong>New Comment:</strong> {comment}</p>' if comment else ''}
            <p>You can view the full details in your dashboard.</p>
        </body>
    </html>
    """

    # Send emails in background
    background_tasks.add_task(send_email, tenant.email, subject, html_content)
    background_tasks.add_task(send_email, property_owner.email, subject, html_content)

def notify_case_closed(background_tasks: BackgroundTasks, ticket: Ticket, db: Session):
    """Send notification when a case is closed."""
    # Get tenant email
    tenant = db.query(User).filter(User.id == ticket.user_id).first()
    if not tenant:
        return

    # Get property owner email
    property_owner = db.query(User).filter(
        User.id == ticket.property.owner_id
    ).first()
    if not property_owner:
        return

    # Prepare email content
    subject = f"Case Closed: {ticket.title}"
    html_content = f"""
    <html>
        <body>
            <h2>Case Closed</h2>
            <p><strong>Case ID:</strong> {ticket.id}</p>
            <p><strong>Title:</strong> {ticket.title}</p>
            <p><strong>Resolution:</strong> {ticket.staff_response or 'No resolution provided'}</p>
            <p>Thank you for using our support system. If you have any further questions, please don't hesitate to create a new case.</p>
        </body>
    </html>
    """

    # Send emails in background
    background_tasks.add_task(send_email, tenant.email, subject, html_content)
    background_tasks.add_task(send_email, property_owner.email, subject, html_content) 