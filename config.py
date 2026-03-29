import os

DATABASE_URL = os.getenv("DATABASE_URL")
REDIS_URL = os.getenv("REDIS_URL")

JWT_SECRET = os.getenv("JWT_SECRET", "supersecret")

PAYSTACK_SECRET = os.getenv("PAYSTACK_SECRET_KEY")

VTU_USERNAME = os.getenv("VTU_USERNAME")
VTU_API_KEY = os.getenv("VTU_API_KEY")
