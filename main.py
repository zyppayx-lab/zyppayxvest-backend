from fastapi import FastAPI
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.orm import sessionmaker, declarative_base
from fastapi.middleware.cors import CORSMiddleware
import os

app = FastAPI()

# ✅ CORS (fixes "Failed to fetch")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# DATABASE
DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

# MODEL
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True)
    password = Column(String)
    full_name = Column(String)
    balance = Column(Integer, default=0)

# CREATE TABLE
Base.metadata.create_all(bind=engine)

# REQUEST MODELS
class UserCreate(BaseModel):
    email: str
    password: str
    full_name: str

class UserLogin(BaseModel):
    email: str
    password: str

# ROUTES
@app.get("/")
def home():
    return {"message": "Zyppayx API running 🚀"}

@app.post("/signup")
def signup(user: UserCreate):
    db = SessionLocal()

    existing = db.query(User).filter(User.email == user.email).first()
    if existing:
        return {"detail": "User already exists"}

    new_user = User(
        email=user.email,
        password=user.password,
        full_name=user.full_name
    )

    db.add(new_user)
    db.commit()

    return {"message": "User created"}

@app.post("/login")
def login(user: UserLogin):
    db = SessionLocal()

    existing = db.query(User).filter(User.email == user.email).first()

    if not existing or existing.password != user.password:
        return {"detail": "Invalid credentials"}

    return {
        "access_token": "demo-token",
        "user": {
            "email": existing.email,
            "full_name": existing.full_name,
            "balance": existing.balance
        }
    }
