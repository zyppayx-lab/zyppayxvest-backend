from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.orm import sessionmaker, declarative_base
from fastapi.middleware.cors import CORSMiddleware
import requests
import os

app = FastAPI()

# ✅ CORS (fix fetch issues)
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

# ================= PAYSTACK =================
PAYSTACK_SECRET = os.getenv("PAYSTACK_SECRET_KEY")

# ================= ROUTES =================

@app.get("/")
def home():
    return {"message": "Zyppayx API running 🚀"}


# ✅ SIGNUP
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


# ✅ LOGIN
@app.post("/login")
def login(user: UserLogin):
    db = SessionLocal()

    existing = db.query(User).filter(User.email == user.email).first()

    if not existing or existing.password != user.password:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    return {
        "access_token": "token",
        "user": {
            "email": existing.email,
            "full_name": existing.full_name,
            "balance": existing.balance
        }
    }


# ✅ SET PIN
@app.post("/set-pin")
def set_pin(data: PinData):
    db = SessionLocal()

    user = db.query(User).filter(User.email == data.email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.pin = data.pin
    db.commit()

    return {"message": "PIN set successfully"}


# ✅ GET USER
@app.get("/user/{email}")
def get_user(email: str):
    db = SessionLocal()

    user = db.query(User).filter(User.email == email).first()

    return {
        "email": user.email,
        "full_name": user.full_name,
        "balance": user.balance
    }


# ================= 💰 PAYSTACK DEPOSIT =================

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

    return {
        "payment_url": response["data"]["authorization_url"]
    }


# 🔔 WEBHOOK (AUTO CREDIT)
@app.post("/paystack-webhook")
async def paystack_webhook(request: Request):
    body = await request.json()

    if body.get("event") == "charge.success":
        email = body["data"]["customer"]["email"]
        amount = body["data"]["amount"] // 100

        db = SessionLocal()
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


# ================= 💸 WITHDRAW =================

@app.post("/withdraw")
def withdraw(data: WithdrawData):
    db = SessionLocal()

    user = db.query(User).filter(User.email == data.email).first()

    if user.pin != data.pin:
        raise HTTPException(status_code=400, detail="Wrong PIN")

    if user.balance < data.amount:
        raise HTTPException(status_code=400, detail="Insufficient balance")

    user.balance -= data.amount

    tx = Transaction(
        email=data.email,
        amount=data.amount,
        type="withdraw"
    )

    db.add(tx)
    db.commit()

    return {"message": "Withdrawal successful"}


# ================= 📈 INVEST =================

@app.post("/invest")
def invest(data: InvestData):
    db = SessionLocal()

    user = db.query(User).filter(User.email == data.email).first()

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


# COMPLETE INVESTMENTS
@app.post("/complete-investments/{email}")
def complete_investments(email: str):
    db = SessionLocal()

    investments = db.query(Investment).filter(
        Investment.email == email,
        Investment.status == "active"
    ).all()

    user = db.query(User).filter(User.email == email).first()

    for inv in investments:
        total = inv.amount + inv.profit

        user.balance += total
        inv.status = "completed"

        tx = Transaction(
            email=email,
            amount=total,
            type="investment_profit"
        )
        db.add(tx)

    db.commit()

    return {"message": "Investments completed"}


# ================= 📊 TRANSACTIONS =================

@app.get("/transactions/{email}")
def history(email: str):
    db = SessionLocal()

    txs = db.query(Transaction).filter(Transaction.email == email).all()

    return txs

# ================= 🔐 VERIFY PAYMENT =================

@app.get("/verify-payment/{reference}")
def verify_payment(reference: str):
    url = f"https://api.paystack.co/transaction/verify/{reference}"

    headers = {
        "Authorization": f"Bearer {PAYSTACK_SECRET}"
    }

    res = requests.get(url, headers=headers)
    data = res.json()

    if not data.get("status"):
        raise HTTPException(status_code=400, detail="Verification failed")

    return data


# ================= 🔔 IMPROVED WEBHOOK =================

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
