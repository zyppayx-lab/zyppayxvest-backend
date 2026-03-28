# ================= IMPORTS =================
from fastapi import FastAPI, HTTPException, Depends, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.orm import sessionmaker, declarative_base
from jose import jwt
from cryptography.fernet import Fernet
from datetime import datetime, timedelta
from pydantic import BaseModel
import requests
import os
import uuid
import hashlib
import redis
import bcrypt
import logging
import hmac
import time

# ================= INIT =================
app = FastAPI()
logging.basicConfig(level=logging.INFO)

# ================= ENV =================
DATABASE_URL = os.getenv("DATABASE_URL")
JWT_SECRET = os.getenv("JWT_SECRET")
FERNET_KEY = os.getenv("FERNET_KEY")
PAYSTACK_SECRET = os.getenv("PAYSTACK_SECRET_KEY")
REDIS_URL = os.getenv("REDIS_URL")
MAILERSEND_API_KEY = os.getenv("MAILERSEND_API_KEY")
SENDER_EMAIL = os.getenv("SENDER_EMAIL")

# ================= SETUP =================
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

r = redis.from_url(REDIS_URL, decode_responses=True)
cipher = Fernet(FERNET_KEY)

security = HTTPBearer()
ALGO = "HS256"

# ================= HELPERS =================

def hash_password(p): return bcrypt.hashpw(p.encode(), bcrypt.gensalt()).decode()
def verify_password(p, h): return bcrypt.checkpw(p.encode(), h.encode())
def hash_pin(p): return hashlib.sha256(p.encode()).hexdigest()

def encrypt(t): return cipher.encrypt(t.encode()).decode()
def decrypt(t): return cipher.decrypt(t.encode()).decode()

def create_access(email):
    return jwt.encode({"sub": email, "exp": datetime.utcnow() + timedelta(minutes=30)}, JWT_SECRET, algorithm=ALGO)

def create_refresh(email):
    return jwt.encode({"sub": email, "type": "refresh", "exp": datetime.utcnow() + timedelta(days=7)}, JWT_SECRET, algorithm=ALGO)

def get_user(token: HTTPAuthorizationCredentials = Depends(security)):
    try:
        payload = jwt.decode(token.credentials, JWT_SECRET, algorithms=[ALGO])
        email = payload.get("sub")
    except:
        raise HTTPException(401, "Invalid token")

    db = SessionLocal()
    user = db.query(User).filter_by(email=email).first()
    if not user:
        raise HTTPException(404, "User not found")
    return user

def admin_only(user=Depends(get_user)):
    if user.role != "admin":
        raise HTTPException(403, "Admin only")
    return user

# ================= REDIS OTP =================

def save_otp(email, otp):
    r.set(f"otp:{email}", otp, ex=300)

def verify_otp(email, otp):
    stored = r.get(f"otp:{email}")
    if not stored or stored != otp:
        return False
    r.delete(f"otp:{email}")
    return True

# ================= EMAIL =================

def send_email(to, subject, message):
    requests.post(
        "https://api.mailersend.com/v1/email",
        headers={"Authorization": f"Bearer {MAILERSEND_API_KEY}"},
        json={
            "from": {"email": SENDER_EMAIL},
            "to": [{"email": to}],
            "subject": subject,
            "text": message
        }
    )

def notify(user, subject, msg):
    send_email(user.email, subject, msg)

# ================= MODELS =================

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, index=True)
    password = Column(String)
    pin = Column(String)
    role = Column(String, default="user")
    refresh_token = Column(String)

    account_number = Column(String)
    bank_code = Column(String)
    recipient_code = Column(String)

class Wallet(Base):
    __tablename__ = "wallets"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, index=True)
    currency = Column(String)
    balance = Column(Integer, default=0)
    pending_balance = Column(Integer, default=0)

class Transaction(Base):
    __tablename__ = "transactions"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, index=True)
    amount = Column(Integer)
    currency = Column(String)
    type = Column(String)
    status = Column(String)
    reference = Column(String, unique=True, index=True)

class Ledger(Base):
    __tablename__ = "ledger"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer)
    currency = Column(String)
    amount = Column(Integer)
    before_balance = Column(Integer)
    after_balance = Column(Integer)
    reference = Column(String)

Base.metadata.create_all(bind=engine)

# ================= REQUESTS =================

class Signup(BaseModel):
    email: str
    password: str

class Login(BaseModel):
    email: str
    password: str

class OTP(BaseModel):
    email: str
    otp: str

class Withdraw(BaseModel):
    amount: int
    currency: str
    pin: str

class Bank(BaseModel):
    account_number: str
    bank_code: str

# ================= AUTH =================

@app.post("/signup")
def signup(data: Signup):
    db = SessionLocal()

    if db.query(User).filter_by(email=data.email).first():
        raise HTTPException(400, "User exists")

    user = User(email=data.email, password=hash_password(data.password))
    db.add(user)
    db.commit()

    for c in ["NGN","USD","GHS","KES"]:
        db.add(Wallet(user_id=user.id, currency=c))

    db.commit()
    return {"msg": "Account created"}

@app.post("/login")
def login(data: Login):
    db = SessionLocal()
    user = db.query(User).filter_by(email=data.email).first()

    if not user or not verify_password(data.password, user.password):
        raise HTTPException(401, "Invalid credentials")

    otp = str(uuid.uuid4())[:6]
    save_otp(data.email, otp)
    send_email(data.email, "Login OTP", otp)

    return {"msg": "OTP sent"}

@app.post("/verify-login")
def verify_login(data: OTP):
    if not verify_otp(data.email, data.otp):
        raise HTTPException(400, "Invalid OTP")

    db = SessionLocal()
    user = db.query(User).filter_by(email=data.email).first()

    access = create_access(user.email)
    refresh = create_refresh(user.email)

    user.refresh_token = refresh
    db.commit()

    return {"access": access, "refresh": refresh}

# ================= WITHDRAW =================

@app.post("/withdraw")
def withdraw(data: Withdraw, user: User = Depends(get_user)):
    db = SessionLocal()

    wallet = db.query(Wallet)\
        .filter_by(user_id=user.id, currency=data.currency)\
        .with_for_update()\
        .first()

    if wallet.balance < data.amount:
        raise HTTPException(400, "Insufficient")

    if user.pin != hash_pin(data.pin):
        raise HTTPException(400, "Wrong PIN")

    ref = str(uuid.uuid4())

    wallet.pending_balance += data.amount

    db.add(Transaction(
        user_id=user.id,
        amount=data.amount,
        currency=data.currency,
        type="withdraw",
        status="pending",
        reference=ref
    ))

    db.commit()

    notify(user, "Withdrawal Requested", f"{data.amount} pending")

    return {"msg": "Pending approval"}

# ================= WEBHOOK =================

@app.post("/webhook/paystack")
async def webhook(req: Request):
    body = await req.body()

    signature = req.headers.get("x-paystack-signature")
    computed = hmac.new(PAYSTACK_SECRET.encode(), body, hashlib.sha512).hexdigest()

    if signature != computed:
        raise HTTPException(400, "Invalid signature")

    payload = await req.json()
    event = payload.get("event")

    db = SessionLocal()

    if event == "transfer.success":
        ref = payload["data"]["reference"]
        tx = db.query(Transaction).filter_by(reference=ref).first()

        if tx and tx.status != "approved":
            wallet = db.query(Wallet)\
                .filter_by(user_id=tx.user_id, currency=tx.currency)\
                .with_for_update()\
                .first()

            wallet.pending_balance -= tx.amount
            wallet.balance -= tx.amount

            tx.status = "approved"
            db.commit()

    return {"status": "ok"}

# ================= ADMIN =================

@app.post("/admin/approve")
def approve(tx_id: int, admin=Depends(admin_only)):
    from celery_worker import process_transfer

    db = SessionLocal()
    tx = db.query(Transaction).filter_by(id=tx_id).first()

    if tx.status != "pending":
        raise HTTPException(400, "Already processed")

    user = db.query(User).filter_by(id=tx.user_id).first()

    transfer_ref = str(uuid.uuid4())

    process_transfer.delay(user.recipient_code, tx.amount, transfer_ref)

    tx.status = "processing"
    tx.reference = transfer_ref

    db.commit()

    return {"msg": "Transfer queued"}
