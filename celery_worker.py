from celery import Celery
import os, requests

celery = Celery(
    "worker",
    broker=os.getenv("REDIS_URL"),
    backend=os.getenv("REDIS_URL")
)

PAYSTACK_SECRET = os.getenv("PAYSTACK_SECRET_KEY")

@celery.task(bind=True, max_retries=5)
def process_transfer(self, recipient_code, amount, reference):
    try:
        res = requests.post(
            "https://api.paystack.co/transfer",
            headers={"Authorization": f"Bearer {PAYSTACK_SECRET}"},
            json={
                "source": "balance",
                "amount": amount * 100,
                "recipient": recipient_code,
                "reference": reference
            }
        ).json()

        if not res.get("status"):
            raise Exception("Transfer failed")

        return res

    except Exception as e:
        raise self.retry(exc=e, countdown=10)
