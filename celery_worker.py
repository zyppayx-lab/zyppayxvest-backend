from celery import Celery
import requests, time
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from config import *
from models import Transaction, Wallet

celery = Celery("worker", broker=REDIS_URL, backend=REDIS_URL)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)

@celery.task(bind=True, max_retries=3)
def process_airtime(self, tx_id, network, phone, amount):
    db = SessionLocal()

    tx = db.query(Transaction).filter_by(id=tx_id).first()
    wallet = db.query(Wallet).filter_by(user_id=tx.user_id).first()

    if not tx or tx.status == "success":
        return

    try:
        for _ in range(3):
            res = requests.get(
                "https://www.nellobytesystems.com/APIAirtimeV1.asp",
                params={
                    "UserID": VTU_USERNAME,
                    "APIKey": VTU_API_KEY,
                    "MobileNetwork": network,
                    "Amount": amount,
                    "MobileNumber": phone,
                    "RequestID": tx.reference
                },
                timeout=15
            )

            if "successful" in res.text.lower():
                tx.status = "success"
                wallet.balance += amount * 0.03
                db.commit()
                return

            time.sleep(2)

        raise Exception("failed")

    except Exception as e:
        tx.status = "failed"
        wallet.balance += amount
        db.commit()
        self.retry(exc=e, countdown=30)
