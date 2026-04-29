"""
T2 RBAC System — Data Models

Define SQLAlchemy models here.
Requirements:
- Tenant: id, name
- User: id, tenant_id (FK), username (unique), password_hash, created_at
- Role: id, tenant_id (FK), name, parent_role_id (nullable self-ref FK)
- Permission: id, code (e.g. doc.read, doc.write, doc.delete, doc.write.any, role.manage)
- role_permissions: many-to-many (role_id, permission_id)
- user_roles: many-to-many (user_id, role_id)
- Document: id, tenant_id (FK), owner_id (FK to User), title, content
"""

from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from app import db

# Many-to-many association tables
role_permissions = db.Table('role_permissions',
    db.Column('role_id', db.Integer, db.ForeignKey('role.id'), primary_key=True),
    db.Column('permission_id', db.Integer, db.ForeignKey('permission.id'), primary_key=True)
)

user_roles = db.Table('user_roles',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('role_id', db.Integer, db.ForeignKey('role.id'), primary_key=True)
)


class Tenant(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    users = db.relationship('User', backref='tenant', lazy=True)
    roles = db.relationship('Role', backref='tenant', lazy=True)
    documents = db.relationship('Document', backref='tenant', lazy=True)


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=False)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    roles = db.relationship('Role', secondary=user_roles, backref='users')


class Role(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=False)
    name = db.Column(db.String(80), nullable=False)
    parent_role_id = db.Column(db.Integer, db.ForeignKey('role.id'), nullable=True)
    permissions = db.relationship('Permission', secondary=role_permissions, backref='roles')


class Permission(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(100), unique=True, nullable=False)


class Document(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=False)
    owner_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, default='')
    owner = db.relationship('User', backref='documents')
