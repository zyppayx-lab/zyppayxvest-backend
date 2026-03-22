from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from jose import jwt
from datetime import datetime, timedelta
import hashlib

app = FastAPI()

SECRET_KEY = "supersecretkey"
ALGORITHM = "HS256"

users = {}

class UserSignup(BaseModel):
    email: str
    password: str
    full_name: str

class UserLogin(BaseModel):
    email: str
    password: str


def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(password, hashed):
    return hash_password(password) == hashed

def create_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(hours=24)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


@app.get("/")
def home():
    return {"message": "Zyppayx API running 🚀"}


@app.post("/signup")
def signup(user: UserSignup):
    if user.email in users:
        raise HTTPException(status_code=400, detail="User already exists")

    users[user.email] = {
        "full_name": user.full_name,
        "password": hash_password(user.password),
        "balance": 0
    }

    return {"message": "Account created successfully"}


@app.post("/login")
def login(user: UserLogin):
    db_user = users.get(user.email)

    if not db_user or not verify_password(user.password, db_user["password"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_token({"sub": user.email})

    return {
        "access_token": token,
        "user": {
            "email": user.email,
            "full_name": db_user["full_name"],
            "balance": db_user["balance"]
        }
    }
