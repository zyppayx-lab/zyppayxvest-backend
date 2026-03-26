from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, DateTime
from sqlalchemy.orm import sessionmaker, declarative_base
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
import requests
import os

app = FastAPI()

# ================= CORS =================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ================= DATABASE =================
DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

# ================= MODELS =================

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True)
    password = Column(String)
    full_name = Column(String)
    balance = Column(Integer, default=0)
    pin = Column(String, default="")

class Transaction(Base):
    __tablename__ = "transactions"
    id = Column(Integer, primary_key=True)
    email = Column(String)
    amount = Column(Integer)
    type = Column(String)

class Investment(Base):
    __tablename__ = "investments"
    id = Column(Integer, primary_key=True)
    email = Column(String)
    amount = Column(Integer)
    profit = Column(Integer)
    status = Column(String, default="active")
    created_at = Column(DateTime, default=datetime.utcnow)

class Bank(Base):
    __tablename__ = "banks"
    id = Column(Integer, primary_key=True)
    email = Column(String)
    account_number = Column(String)
    bank_code = Column(String)
    recipient_code = Column(String)

Base.metadata.create_all(bind=engine)

# ================= REQUEST MODELS =================

class UserCreate(BaseModel):
    email: str
    password: str
    full_name: str

class UserLogin(BaseModel):
    email: str
    password: str

class PinData(BaseModel):
    email: str
    pin: str

class DepositData(BaseModel):
    email: str
    amount: int

class WithdrawData(BaseModel):
    email: str
    amount: int
    pin: str

class InvestData(BaseModel):
    email: str
    amount: int

class BankData(BaseModel):
    email: str
    account_number: str
    bank_code: str

# ================= PAYSTACK =================
PAYSTACK_SECRET = os.getenv("PAYSTACK_SECRET_KEY")

# ================= ROUTES =================

@app.get("/")
def home():
    return {"message": "Zyppayx API running 🚀"}

# ================= AUTH =================

@app.post("/signup")
def signup(user: UserCreate):
    db = SessionLocal()

    existing = db.query(User).filter(User.email == user.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="User exists")

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

    user_db = db.query(User).filter(User.email == user.email).first()

    if not user_db or user_db.password != user.password:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    return {
        "access_token": "token",
        "user": {
            "email": user_db.email,
            "full_name": user_db.full_name,
            "balance": user_db.balance
        }
    }

# ================= PIN =================

@app.post("/set-pin")
def set_pin(data: PinData):
    db = SessionLocal()

    user = db.query(User).filter(User.email == data.email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.pin = data.pin
    db.commit()

    return {"message": "PIN set successfully"}

# ================= USER =================

@app.get("/user/{email}")
def get_user(email: str):
    db = SessionLocal()

    user = db.query(User).filter(User.email == email).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return {
        "email": user.email,
        "full_name": user.full_name,
        "balance": user.balance
    }

# ================= DEPOSIT =================

@app.post("/create-payment")
def create_payment(data: DepositData):
    url = "https://api.paystack.co/transaction/initialize"

    headers = {
        "Authorization": f"Bearer {PAYSTACK_SECRET}",
        "Content-Type": "application/json"
    }

    payload = {
        "email": data.email,
        "amount": data.amount * 100,
        "callback_url": "https://zyppayx.name.ng/payment-success.html"
    }

    res = requests.post(url, json=payload, headers=headers)
    response = res.json()

    if not response.get("status"):
        raise HTTPException(status_code=400, detail="Payment init failed")

    return {"payment_url": response["data"]["authorization_url"]}

# ================= WEBHOOK =================

@app.post("/paystack-webhook")
async def paystack_webhook(request: Request):
    body = await request.json()

    if body.get("event") == "charge.success":
        email = body["data"]["customer"]["email"]
        amount = body["data"]["amount"] // 100

        db = SessionLocal()

        existing = db.query(Transaction).filter(
            Transaction.email == email,
            Transaction.amount == amount,
            Transaction.type == "deposit"
        ).first()

        if existing:
            return {"status": "already processed"}

        user = db.query(User).filter(User.email == email).first()

        if user:
            user.balance += amount

            tx = Transaction(
                email=email,
                amount=amount,
                type="deposit"
            )

            db.add(tx)
            db.commit()

    return {"status": "ok"}

# ================= BANK =================

@app.post("/add-bank")
def add_bank(data: BankData):
    url = "https://api.paystack.co/transferrecipient"

    headers = {
        "Authorization": f"Bearer {PAYSTACK_SECRET}",
        "Content-Type": "application/json"
    }

    payload = {
        "type": "nuban",
        "name": data.email,
        "account_number": data.account_number,
        "bank_code": data.bank_code,
        "currency": "NGN"
    }

    res = requests.post(url, json=payload, headers=headers)
    response = res.json()

    if not response.get("status"):
        raise HTTPException(status_code=400, detail="Bank verification failed")

    recipient_code = response["data"]["recipient_code"]

    db = SessionLocal()

    bank = Bank(
        email=data.email,
        account_number=data.account_number,
        bank_code=data.bank_code,
        recipient_code=recipient_code
    )

    db.add(bank)
    db.commit()

    return {"message": "Bank added successfully"}

# ================= WITHDRAW =================

@app.post("/withdraw")
def withdraw(data: WithdrawData):
    db = SessionLocal()

    user = db.query(User).filter(User.email == data.email).first()
    bank = db.query(Bank).filter(Bank.email == data.email).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if not bank:
        raise HTTPException(status_code=400, detail="Add bank first")

    if user.pin != data.pin:
        raise HTTPException(status_code=400, detail="Wrong PIN")

    if user.balance < data.amount:
        raise HTTPException(status_code=400, detail="Insufficient balance")

    url = "https://api.paystack.co/transfer"

    headers = {
        "Authorization": f"Bearer {PAYSTACK_SECRET}",
        "Content-Type": "application/json"
    }

    payload = {
        "source": "balance",
        "amount": data.amount * 100,
        "recipient": bank.recipient_code,
        "reason": "Withdrawal"
    }

    res = requests.post(url, json=payload, headers=headers)
    response = res.json()

    if not response.get("status"):
        raise HTTPException(status_code=400, detail="Transfer failed")

    user.balance -= data.amount

    tx = Transaction(
        email=data.email,
        amount=data.amount,
        type="withdraw"
    )

    db.add(tx)
    db.commit()

    return {"message": "Withdrawal successful"}

# ================= INVEST =================

@app.post("/invest")
def invest(data: InvestData):
    db = SessionLocal()

    user = db.query(User).filter(User.email == data.email).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.balance < data.amount:
        raise HTTPException(status_code=400, detail="Insufficient balance")

    user.balance -= data.amount

    profit = int(data.amount * 0.3)

    inv = Investment(
        email=data.email,
        amount=data.amount,
        profit=profit
    )

    db.add(inv)
    db.commit()

    return {"message": "Investment started"}

# ================= TRANSACTIONS =================

@app.get("/transactions/{email}")
def history(email: str):
    db = SessionLocal()

    txs = db.query(Transaction).filter(Transaction.email == email).all()

    return txs
