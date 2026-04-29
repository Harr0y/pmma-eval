"""
T2 Order System — Data Models

Define SQLAlchemy models here.
Requirements:
- Product: id, name, price (float), stock (int)
- Order: id, user_id (string), status (string), total_amount (float),
         created_at, paid_at, shipped_at, delivered_at, cancelled_at
- OrderItem: id, order_id (FK), product_id (FK), quantity (int), unit_price (float)
- PaymentRequest: id, order_id (FK), idempotency_key (string), status (string), created_at

Order status values: 'pending', 'paid', 'shipped', 'delivered', 'cancelled'
"""

from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from app import db


class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    price = db.Column(db.Float, nullable=False)
    stock = db.Column(db.Integer, nullable=False, default=0)


class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(50), nullable=False)
    status = db.Column(db.String(20), nullable=False, default='pending')
    total_amount = db.Column(db.Float, nullable=False, default=0.0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    paid_at = db.Column(db.DateTime, nullable=True)
    shipped_at = db.Column(db.DateTime, nullable=True)
    delivered_at = db.Column(db.DateTime, nullable=True)
    cancelled_at = db.Column(db.DateTime, nullable=True)
    items = db.relationship('OrderItem', backref='order', lazy=True)


class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    unit_price = db.Column(db.Float, nullable=False)


class PaymentRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    idempotency_key = db.Column(db.String(200), nullable=False, unique=True)
    status = db.Column(db.String(20), nullable=False, default='pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
