from typing import Dict, List, Optional
import openai
from pydantic import BaseModel
from fastapi import HTTPException
import os
from dotenv import load_dotenv

load_dotenv()

# Initialize OpenAI client
openai.api_key = os.getenv("OPENAI_API_KEY")

class EmailCategory(BaseModel):
    category: str
    confidence: float
    department: str
    priority: str

class EmailClassifier:
    CATEGORIES = {
        "complaint": {
            "department": "Customer Service",
            "priority": "high",
            "description": "Customer complaints and dissatisfaction"
        },
        "rent_issue": {
            "department": "Finance",
            "priority": "high",
            "description": "Rent payment issues and queries"
        },
        "service_request": {
            "department": "Maintenance",
            "priority": "medium",
            "description": "Maintenance and repair requests"
        },
        "general_inquiry": {
            "department": "General Support",
            "priority": "low",
            "description": "General questions and information requests"
        }
    }

    @staticmethod
    async def classify_email(email_content: str) -> EmailCategory:
        try:
            # Prepare the prompt for classification
            prompt = f"""Classify the following email into one of these categories: {', '.join(EmailClassifier.CATEGORIES.keys())}
            Email content: {email_content}
            Provide the classification in JSON format with category, confidence score (0-1), and explanation."""

            # Call OpenAI API
            response = await openai.ChatCompletion.acreate(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "You are an email classification expert."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=150
            )

            # Parse the response
            classification = response.choices[0].message.content
            # Extract category and confidence from the response
            # This is a simplified version - you might want to add more robust parsing
            category = classification.lower().split()[0]  # Get the first word as category
            confidence = 0.8  # Default confidence score

            if category not in EmailClassifier.CATEGORIES:
                category = "general_inquiry"

            return EmailCategory(
                category=category,
                confidence=confidence,
                department=EmailClassifier.CATEGORIES[category]["department"],
                priority=EmailClassifier.CATEGORIES[category]["priority"]
            )

        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Error classifying email: {str(e)}"
            )

    @staticmethod
    def get_department_email(category: str) -> str:
        """Get the appropriate department email address based on category."""
        department_emails = {
            "complaint": "customer-service@propertypro.com",
            "rent_issue": "finance@propertypro.com",
            "service_request": "maintenance@propertypro.com",
            "general_inquiry": "support@propertypro.com"
        }
        return department_emails.get(category, "support@propertypro.com")

    @staticmethod
    def should_escalate(category: EmailCategory) -> bool:
        """Determine if the email should be escalated based on category and confidence."""
        return (
            category.priority == "high" and category.confidence > 0.7
        ) or category.confidence < 0.5 