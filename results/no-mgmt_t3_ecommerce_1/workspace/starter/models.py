"""
T3 E-commerce — Data Models

Define SQLAlchemy models here.
Requirements:
- User: id, username (unique), role ('admin' or 'user')
- Product: id, name, price (float), stock (int)
- Order: id, user_id (FK to User), product_id (FK to Product),
        quantity (int), total_price (float)
"""

from flask_sqlalchemy import SQLAlchemy

# Import the shared db instance from app module
# NOTE: In this project, db is initialized in app.py and imported here
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from app import db


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    role = db.Column(db.String(20), nullable=False)  # 'admin' or 'user'


class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    price = db.Column(db.Float, nullable=False)
    stock = db.Column(db.Integer, nullable=False)


class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    total_price = db.Column(db.Float, nullable=False)
    origin = db.Column(db.String(20), nullable=False, default='web')
