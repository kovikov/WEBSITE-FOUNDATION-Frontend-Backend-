import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.naive_bayes import MultinomialNB
from sklearn.pipeline import Pipeline
from sklearn.model_selection import train_test_split
import joblib
import os
from typing import List, Dict, Tuple
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class EmailIntentClassifier:
    def __init__(self):
        self.model_path = "models/email_classifier.joblib"
        self.categories = [
            "complaint",
            "rent_issue",
            "service_request",
            "praise",
            "legal",
            "general_inquiry"
        ]
        
        # Sample training data - in production, this would come from a database
        self.training_data = {
            "complaint": [
                "The heating system is not working properly",
                "I've been waiting for maintenance for weeks",
                "The noise from the construction is unbearable",
                "My neighbor is causing disturbances",
                "The property is not being maintained well"
            ],
            "rent_issue": [
                "I need to discuss my rent payment",
                "When is the rent due?",
                "I'm having trouble with the rent payment system",
                "Can I get an extension on my rent?",
                "I need to set up automatic rent payments"
            ],
            "service_request": [
                "The faucet is leaking",
                "Need maintenance for the air conditioning",
                "The door lock is broken",
                "Request for pest control",
                "The garbage disposal is not working"
            ],
            "praise": [
                "Thank you for the quick response",
                "The maintenance team did a great job",
                "I'm very happy with the service",
                "The property is well maintained",
                "The staff is very helpful"
            ],
            "legal": [
                "I need to discuss my lease agreement",
                "There's a dispute with my neighbor",
                "I want to file a formal complaint",
                "Need legal advice about my tenancy",
                "I have questions about my rights as a tenant"
            ],
            "general_inquiry": [
                "What are the office hours?",
                "How do I report a maintenance issue?",
                "Where can I find the community guidelines?",
                "What's the process for renewing my lease?",
                "How do I update my contact information?"
            ]
        }
        
        self.model = None
        self.vectorizer = None

    def prepare_training_data(self) -> Tuple[List[str], List[str]]:
        """Prepare training data from the sample data."""
        texts = []
        labels = []
        
        for category, examples in self.training_data.items():
            texts.extend(examples)
            labels.extend([category] * len(examples))
            
        return texts, labels

    def train(self) -> None:
        """Train the email classifier model."""
        try:
            # Prepare training data
            texts, labels = self.prepare_training_data()
            
            # Split into training and validation sets
            X_train, X_val, y_train, y_val = train_test_split(
                texts, labels, test_size=0.2, random_state=42
            )
            
            # Create and train the pipeline
            self.model = Pipeline([
                ('tfidf', TfidfVectorizer(
                    max_features=5000,
                    stop_words='english',
                    ngram_range=(1, 2)
                )),
                ('clf', MultinomialNB())
            ])
            
            # Train the model
            self.model.fit(X_train, y_train)
            
            # Evaluate the model
            accuracy = self.model.score(X_val, y_val)
            logger.info(f"Model accuracy: {accuracy:.2f}")
            
            # Save the model
            os.makedirs(os.path.dirname(self.model_path), exist_ok=True)
            joblib.dump(self.model, self.model_path)
            logger.info(f"Model saved to {self.model_path}")
            
        except Exception as e:
            logger.error(f"Error training model: {str(e)}")
            raise

    def load_model(self) -> None:
        """Load the trained model from disk."""
        try:
            if os.path.exists(self.model_path):
                self.model = joblib.load(self.model_path)
                logger.info("Model loaded successfully")
            else:
                logger.warning("No trained model found. Training new model...")
                self.train()
        except Exception as e:
            logger.error(f"Error loading model: {str(e)}")
            raise

    def predict(self, text: str) -> Dict[str, float]:
        """Predict the category of an email."""
        try:
            if self.model is None:
                self.load_model()
            
            # Get probability scores for each category
            probas = self.model.predict_proba([text])[0]
            
            # Create a dictionary of category probabilities
            predictions = {
                category: float(prob)
                for category, prob in zip(self.model.classes_, probas)
            }
            
            # Get the most likely category
            predicted_category = max(predictions.items(), key=lambda x: x[1])
            
            return {
                "category": predicted_category[0],
                "confidence": predicted_category[1],
                "probabilities": predictions
            }
            
        except Exception as e:
            logger.error(f"Error making prediction: {str(e)}")
            raise

    def update_training_data(self, text: str, category: str) -> None:
        """Update the training data with new examples."""
        try:
            if category in self.categories:
                self.training_data[category].append(text)
                logger.info(f"Added new training example for category: {category}")
                
                # Retrain the model with the new data
                self.train()
            else:
                logger.warning(f"Invalid category: {category}")
        except Exception as e:
            logger.error(f"Error updating training data: {str(e)}")
            raise

# Example usage
if __name__ == "__main__":
    classifier = EmailIntentClassifier()
    classifier.train()
    
    # Test the classifier
    test_emails = [
        "The heating system is not working and it's freezing in here",
        "I need to pay my rent but the online system is down",
        "The maintenance team did an excellent job fixing my sink",
        "I have a question about my lease agreement"
    ]
    
    for email in test_emails:
        prediction = classifier.predict(email)
        print(f"\nEmail: {email}")
        print(f"Predicted category: {prediction['category']}")
        print(f"Confidence: {prediction['confidence']:.2f}") 