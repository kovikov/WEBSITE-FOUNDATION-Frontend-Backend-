from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class UserBase(BaseModel):
    email: EmailStr
    full_name: str
    role: str

class UserCreate(UserBase):
    password: str

class User(UserBase):
    id: int
    is_active: bool

    class Config:
        from_attributes = True

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class PropertyBase(BaseModel):
    address: str
    property_type: str
    size: float
    bedrooms: int
    bathrooms: int
    rent_amount: float
    status: str

class PropertyCreate(PropertyBase):
    pass

class Property(PropertyBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True

class MaintenanceTicketBase(BaseModel):
    title: str
    description: str
    priority: str
    property_id: int

class MaintenanceTicketCreate(MaintenanceTicketBase):
    pass

class MaintenanceTicket(MaintenanceTicketBase):
    id: int
    status: str
    created_at: datetime
    updated_at: datetime
    user_id: int

    class Config:
        from_attributes = True

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password) 