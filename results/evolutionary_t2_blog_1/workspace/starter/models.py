"""
T2 Blog — Data Models

Define SQLAlchemy models here.
Requirements:
- Article: id, title (non-empty string), body (text)
- Tag: id, name (unique, non-null)
- article_tags: many-to-many association table
"""

from flask_sqlalchemy import SQLAlchemy
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from app import db

# Many-to-many association table
article_tags = db.Table('article_tags',
    db.Column('article_id', db.Integer, db.ForeignKey('article.id'), primary_key=True),
    db.Column('tag_id', db.Integer, db.ForeignKey('tag.id'), primary_key=True)
)


class Article(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    body = db.Column(db.Text, nullable=False)
    tags = db.relationship('Tag', secondary=article_tags,
                           backref=db.backref('articles', lazy='dynamic'))


class Tag(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
