"""
T3 E-commerce — Data Models (Gen 2, Sample 3)

Implementation strategy:
- Add `origin` field to Order model with default value 'web'.
- The origin field is a nullable string column; 'web' is set as the
  Python-level default so that it is always populated when creating
  an Order object without explicitly passing origin.
- All other models remain unchanged from the original models.py.

Evolutionary notes (inherited traits):
- db instance imported from app module (same pattern as models.py).
- sys.path manipulation preserved for module resolution.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from flask_sqlalchemy import SQLAlchemy
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
