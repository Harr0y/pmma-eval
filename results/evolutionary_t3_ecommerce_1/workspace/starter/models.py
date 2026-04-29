"""
T3 E-commerce — Data Models (Sample 1: Value-Object Origin Field)

Mutation Strategy: Instead of a plain db.String column, the Order model
includes an `origin` field with a server-side default of 'web'.  The field
is declared as a plain nullable=False column so the database itself enforces
that every row has a value, even if the application code somehow forgets to
set one.  No ORM-level Python-side default is used here — the route layer
is responsible for supplying the value, keeping the model layer purely
structural.
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
