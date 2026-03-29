from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timedelta
from jose import jwt
import bcrypt, uuid

from config import *
from models import *
from celery_worker import process_airtime

app = FastAPI()
security = HTTPBearer()

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)

Base.metadata.create_all(bind=engine)

# ================= HELPERS =================
def hash_password(p): return bcrypt.hashpw(p.encode(), bcrypt.gensalt()).decode()
def verify_password(p, h): return bcrypt.checkpw(p.encode(), h.encode())

def token(email):
    return jwt.encode({"sub": email, "exp": datetime.utcnow()+timedelta(hours=2)}, JWT_SECRET, algorithm="HS256")

def get_user(t: HTTPAuthorizationCredentials = Depends(security)):
    email = jwt.decode(t.credentials, JWT_SECRET, algorithms=["HS256"])["sub"]
    db = SessionLocal()
    user = db.query(User).filter_by(email=email).first()
    db.close()
    if not user or user.is_blocked:
        raise HTTPException(403)
    return user

def admin_only(user):
    if not user.is_admin:
        raise HTTPException(403)

# ================= AUTH =================
@app.post("/signup")
def signup(email: str, password: str):
    db = SessionLocal()
    u = User(email=email, password=hash_password(password))
    db.add(u); db.commit()
    db.add(Wallet(user_id=u.id)); db.commit()
    return {"msg": "created"}

@app.post("/login")
def login(email: str, password: str):
    db = SessionLocal()
    u = db.query(User).filter_by(email=email).first()
    if not u or not verify_password(password, u.password):
        raise HTTPException(401)
    return {"token": token(u.email)}

# ================= ADMIN =================
@app.post("/admin/credit")
def credit(user_id:int, amount:float, user=Depends(get_user)):
    admin_only(user)
    db = SessionLocal()
    w = db.query(Wallet).filter_by(user_id=user_id).first()
    w.balance += amount

    db.add(Transaction(user_id=user_id, amount=amount, type="admin_credit",
                       status="success", reference=str(uuid.uuid4())))
    db.commit()
    return {"msg": "credited"}

@app.post("/admin/debit")
def debit(user_id:int, amount:float, user=Depends(get_user)):
    admin_only(user)
    db = SessionLocal()
    w = db.query(Wallet).filter_by(user_id=user_id).first()

    if float(w.balance) < amount:
        raise HTTPException(400)

    w.balance -= amount

    db.add(Transaction(user_id=user_id, amount=amount, type="admin_debit",
                       status="success", reference=str(uuid.uuid4())))
    db.commit()
    return {"msg": "debited"}

# ================= VTU =================
@app.post("/vtu/airtime")
def airtime(network:int, phone:str, amount:float, user=Depends(get_user)):
    db = SessionLocal()
    w = db.query(Wallet).filter_by(user_id=user.id).with_for_update().first()

    if float(w.balance) < amount:
        raise HTTPException(400)

    ref = str(uuid.uuid4())

    tx = Transaction(user_id=user.id, amount=amount,
                     type="airtime", status="pending", reference=ref)

    db.add(tx)
    w.balance -= amount
    db.commit()

    process_airtime.delay(tx.id, network, phone, amount)

    return {"msg": "processing", "ref": ref}

# ================= PAYSTACK =================
@app.post("/webhook/paystack")
async def webhook(request: Request):
    data = await request.json()
    ref = data["data"]["reference"]

    db = SessionLocal()
    tx = db.query(Transaction).filter_by(reference=ref).first()

    if tx and tx.status == "success":
        return {"msg": "already"}

    w = db.query(Wallet).filter_by(user_id=tx.user_id).first()
    w.balance += tx.amount
    tx.status = "success"

    db.commit()
    return {"msg": "credited"}

# ================= PRODUCT =================
@app.post("/product/create")
def create_product(name:str, price:float, commission:float, user=Depends(get_user)):
    db = SessionLocal()
    db.add(Product(owner_id=user.id, name=name, price=price, commission=commission))
    db.commit()
    return {"msg": "created"}

@app.post("/product/buy")
def buy(product_id:int, user=Depends(get_user)):
    db = SessionLocal()
    p = db.query(Product).filter_by(id=product_id).first()
    w = db.query(Wallet).filter_by(user_id=user.id).first()

    if float(w.balance) < float(p.price):
        raise HTTPException(400)

    w.balance -= p.price

    owner_wallet = db.query(Wallet).filter_by(user_id=p.owner_id).first()
    owner_wallet.balance += p.price * 0.8

    db.add(Order(product_id=p.id, buyer_id=user.id, amount=p.price, status="success"))

    db.commit()
    return {"msg": "purchased"}
