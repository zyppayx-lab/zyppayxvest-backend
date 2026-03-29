from sqlalchemy import Column, Integer, String, Numeric
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True)
    password = Column(String)
    pin = Column(String)
    level = Column(Integer, default=1)
    is_admin = Column(Integer, default=0)
    is_blocked = Column(Integer, default=0)

class Wallet(Base):
    __tablename__ = "wallets"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer)
    balance = Column(Numeric(12,2), default=0)
    pending_balance = Column(Numeric(12,2), default=0)

class Transaction(Base):
    __tablename__ = "transactions"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer)
    amount = Column(Numeric(12,2))
    type = Column(String)
    status = Column(String)
    reference = Column(String, unique=True)

class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True)
    owner_id = Column(Integer)
    name = Column(String)
    price = Column(Numeric(12,2))
    commission = Column(Numeric(5,2))

class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True)
    product_id = Column(Integer)
    buyer_id = Column(Integer)
    affiliate_id = Column(Integer)
    amount = Column(Numeric(12,2))
    status = Column(String)

class Notification(Base):
    __tablename__ = "notifications"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer)
    message = Column(String)
