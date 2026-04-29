"""
T3 E-commerce — Data Models (Sample 3)

Evolutionary variant: inherits User/Product from base models.py,
adds Order with origin field for channel tracking.

Key design: Order.origin defaults to 'web' via server_default on the
SQLAlchemy column, so even raw-SQL inserts get the correct default.
"""

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
    origin = db.Column(db.String(20), nullable=False, default='web',
                       server_default='web')
