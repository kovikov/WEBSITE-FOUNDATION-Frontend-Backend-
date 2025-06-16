import imaplib
import email
from email.header import decode_header
from typing import List, Dict, Optional
import os
from datetime import datetime
import logging
from .email_classifier import EmailClassifier
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class EmailScanner:
    def __init__(self):
        self.imap_server = os.getenv("IMAP_SERVER", "imap.gmail.com")
        self.imap_port = int(os.getenv("IMAP_PORT", "993"))
        self.email_address = os.getenv("EMAIL_ADDRESS")
        self.email_password = os.getenv("EMAIL_PASSWORD")
        
        # Department routing configuration
        self.department_routes = {
            "complaint": os.getenv("COMPLAINTS_EMAIL", "complaints@propertypro.com"),
            "rent_issue": os.getenv("ARREARS_EMAIL", "arrears@propertypro.com"),
            "service_request": os.getenv("REPAIRS_EMAIL", "repairs@propertypro.com"),
            "legal": os.getenv("LEGAL_EMAIL", "legal@propertypro.com"),
            "praise": os.getenv("CUSTOMER_SERVICE_EMAIL", "customer-service@propertypro.com"),
            "general_inquiry": os.getenv("SUPPORT_EMAIL", "support@propertypro.com")
        }

    def connect(self) -> imaplib.IMAP4_SSL:
        """Establish connection to IMAP server."""
        try:
            imap = imaplib.IMAP4_SSL(self.imap_server, self.imap_port)
            imap.login(self.email_address, self.email_password)
            return imap
        except Exception as e:
            logger.error(f"Failed to connect to IMAP server: {str(e)}")
            raise

    def decode_email_subject(self, subject: str) -> str:
        """Decode email subject from various encodings."""
        decoded_parts = []
        for part, encoding in decode_header(subject):
            if isinstance(part, bytes):
                decoded_parts.append(part.decode(encoding or 'utf-8'))
            else:
                decoded_parts.append(part)
        return ''.join(decoded_parts)

    def get_email_body(self, email_message: email.message.Message) -> str:
        """Extract email body from message."""
        body = ""
        if email_message.is_multipart():
            for part in email_message.walk():
                if part.get_content_type() == "text/plain":
                    try:
                        body += part.get_payload(decode=True).decode()
                    except:
                        body += part.get_payload()
        else:
            try:
                body = email_message.get_payload(decode=True).decode()
            except:
                body = email_message.get_payload()
        return body

    def forward_email(
        self,
        to_email: str,
        subject: str,
        body: str,
        original_sender: str,
        category: str
    ) -> None:
        """Forward email to appropriate department."""
        try:
            msg = MIMEMultipart()
            msg["From"] = self.email_address
            msg["To"] = to_email
            msg["Subject"] = f"[{category.upper()}] {subject}"

            # Add original sender information
            body = f"""
            Original sender: {original_sender}
            Category: {category}
            Received: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
            
            Original message:
            {body}
            """

            msg.attach(MIMEText(body, "plain"))

            with smtplib.SMTP(os.getenv("SMTP_SERVER", "smtp.gmail.com"), 
                            int(os.getenv("SMTP_PORT", "587"))) as server:
                server.starttls()
                server.login(self.email_address, self.email_password)
                server.send_message(msg)

            logger.info(f"Email forwarded to {to_email}")

        except Exception as e:
            logger.error(f"Failed to forward email: {str(e)}")
            raise

    async def process_unread_emails(self) -> List[Dict]:
        """Process all unread emails in the inbox."""
        processed_emails = []
        
        try:
            imap = self.connect()
            imap.select("INBOX")
            
            # Search for unread emails
            _, message_numbers = imap.search(None, "UNSEEN")
            
            for num in message_numbers[0].split():
                try:
                    # Fetch email message
                    _, msg_data = imap.fetch(num, "(RFC822)")
                    email_body = msg_data[0][1]
                    email_message = email.message_from_bytes(email_body)
                    
                    # Extract email details
                    subject = self.decode_email_subject(email_message["subject"])
                    sender = email.utils.parseaddr(email_message["from"])[1]
                    body = self.get_email_body(email_message)
                    
                    # Classify email
                    category = await EmailClassifier.classify_email(body)
                    
                    # Forward to appropriate department
                    if category.category in self.department_routes:
                        self.forward_email(
                            self.department_routes[category.category],
                            subject,
                            body,
                            sender,
                            category.category
                        )
                    
                    # Mark as processed
                    processed_emails.append({
                        "id": num.decode(),
                        "subject": subject,
                        "sender": sender,
                        "category": category.category,
                        "processed_at": datetime.now().isoformat()
                    })
                    
                except Exception as e:
                    logger.error(f"Error processing email {num}: {str(e)}")
                    continue
            
            imap.close()
            imap.logout()
            
            return processed_emails
            
        except Exception as e:
            logger.error(f"Error in process_unread_emails: {str(e)}")
            raise

    async def run_email_scan(self) -> None:
        """Main method to run the email scanning process."""
        try:
            processed = await self.process_unread_emails()
            logger.info(f"Processed {len(processed)} emails")
            return processed
        except Exception as e:
            logger.error(f"Email scan failed: {str(e)}")
            raise 