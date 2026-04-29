"""
T2 Blog — Article Routes

Implement article CRUD and tag-binding routes.
Register as a Flask Blueprint named 'article_bp'.

Requirements:
- GET /articles -> List all articles
  Optional query params: tag (filter by tag name), tag_id (filter by tag ID)
  Response: {"status": "ok", "data": [{"id": int, "title": str, "body": str}, ...]}

- POST /articles -> Create article
  Request: {"title": str, "body": str}
  Response: {"status": "ok", "data": {"id": int, "title": str, "body": str}}
  Errors: 400 if title or body missing

- GET /articles/<id> -> Get single article
  Response: {"status": "ok", "data": {"id": int, "title": str, "body": str}}
  Errors: 404 if not found

- POST /articles/<id>/tags -> Bind tags to article
  Request: {"tag_ids": [int, ...]}
  Response: {"status": "ok", "data": {"message": "Tags bound"}}
  Errors: 404 if article not found, 400 if tag not found

- GET /articles/<id>/tags -> Get article's tags
  Response: {"status": "ok", "data": [{"id": int, "name": str}, ...]}
  Errors: 404 if article not found

- DELETE /articles/<id>/tags/<tag_id> -> Unbind tag from article
  Response: {"status": "ok", "data": {"message": "Tag unbound"}}
  Errors: 404 if article not found

IMPORTANT: This module works with models.py (Article, Tag, article_tags) and
routes_tag.py. Make sure field names and response formats are consistent.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from flask import Blueprint, request, jsonify
from app import db
from models import Article, Tag

article_bp = Blueprint('article_bp', __name__)


@article_bp.route('/articles', methods=['GET'])
def list_articles():
    """List all articles, optionally filtered by tag name or tag ID."""
    tag_name = request.args.get('tag')
    tag_id = request.args.get('tag_id')

    if tag_name:
        tag = Tag.query.filter_by(name=tag_name).first()
        if tag:
            articles = tag.articles.all()
        else:
            articles = []
    elif tag_id:
        tag = Tag.query.get(int(tag_id))
        if tag:
            articles = tag.articles.all()
        else:
            articles = []
    else:
        articles = Article.query.all()

    return jsonify({
        'status': 'ok',
        'data': [{'id': a.id, 'title': a.title, 'body': a.body} for a in articles]
    }), 200


@article_bp.route('/articles', methods=['POST'])
def create_article():
    """Create a new article. Requires title and body."""
    data = request.get_json(silent=True) or {}
    title = data.get('title')
    body = data.get('body')
    if not title or not body:
        return jsonify({'status': 'error', 'message': 'title and body are required'}), 400
    article = Article(title=title, body=body)
    db.session.add(article)
    db.session.commit()
    return jsonify({
        'status': 'ok',
        'data': {'id': article.id, 'title': article.title, 'body': article.body}
    }), 201


@article_bp.route('/articles/<int:article_id>', methods=['GET'])
def get_article(article_id):
    """Get a single article by ID."""
    article = Article.query.get(article_id)
    if not article:
        return jsonify({'status': 'error', 'message': 'Article not found'}), 404
    return jsonify({
        'status': 'ok',
        'data': {'id': article.id, 'title': article.title, 'body': article.body}
    }), 200


@article_bp.route('/articles/<int:article_id>/tags', methods=['POST'])
def bind_tags(article_id):
    """Bind tags to an article. Request body: {"tag_ids": [1, 2, ...]}"""
    article = Article.query.get(article_id)
    if not article:
        return jsonify({'status': 'error', 'message': 'Article not found'}), 404

    data = request.get_json(silent=True) or {}
    tag_ids = data.get('tag_ids', [])

    for tid in tag_ids:
        tag = Tag.query.get(tid)
        if not tag:
            return jsonify({'status': 'error', 'message': 'Tag not found'}), 400
        if tag not in article.tags:
            article.tags.append(tag)

    db.session.commit()
    return jsonify({'status': 'ok', 'data': {'message': 'Tags bound'}}), 200


@article_bp.route('/articles/<int:article_id>/tags', methods=['GET'])
def get_article_tags(article_id):
    """Get all tags bound to an article."""
    article = Article.query.get(article_id)
    if not article:
        return jsonify({'status': 'error', 'message': 'Article not found'}), 404
    return jsonify({
        'status': 'ok',
        'data': [{'id': t.id, 'name': t.name} for t in article.tags]
    }), 200


@article_bp.route('/articles/<int:article_id>/tags/<int:tag_id>', methods=['DELETE'])
def unbind_tag(article_id, tag_id):
    """Unbind a tag from an article."""
    article = Article.query.get(article_id)
    if not article:
        return jsonify({'status': 'error', 'message': 'Article not found'}), 404

    tag = Tag.query.get(tag_id)
    if tag and tag in article.tags:
        article.tags.remove(tag)
        db.session.commit()

    return jsonify({'status': 'ok', 'data': {'message': 'Tag unbound'}}), 200
