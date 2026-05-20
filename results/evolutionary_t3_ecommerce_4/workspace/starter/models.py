"""
ATU-003 Sample 2: Data Models — Order gains origin field for channel tracking

Design decisions (distinct from Sample 1):
1. **Minimal delta approach**: Only the Order model is modified; User and Product
   remain byte-for-byte identical to the ATU-002 version, preserving backward
   compatibility with all existing tests and business logic.
2. **origin column with server-side default**: The `origin` column uses
   `default='web'` at the SQLAlchemy level. This means legacy code that creates
   Order objects without specifying origin will automatically get 'web', avoiding
   migration pain.
3. **String(20) constraint**: The origin field is capped at 20 characters to
   prevent abuse while accommodating foreseeable channel names (web, app,
   wechat, miniprogram, etc.).
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
