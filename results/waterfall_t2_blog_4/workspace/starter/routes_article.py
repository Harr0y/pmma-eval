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

from flask import Blueprint, request, jsonify
from models import Article, Tag, db

article_bp = Blueprint('article_bp', __name__)


# --- Serializers (design.md Section 6) ---

def serialize_article(article):
    return {"id": article.id, "title": article.title, "body": article.body}


def serialize_tag(tag):
    return {"id": tag.id, "name": tag.name}


# --- POST /articles — Create article (design.md 2.2) ---

@article_bp.route('/articles', methods=['POST'])
def create_article():
    if not request.is_json:
        return jsonify({"status": "error", "message": "请求体必须是 JSON"}), 400

    data = request.get_json()

    title = data.get('title')
    body = data.get('body')

    if not title or not body:
        missing = []
        if not title:
            missing.append('title')
        if not body:
            missing.append('body')
        return jsonify({"status": "error", "message": f"缺少必填字段: {', '.join(missing)}"}), 400

    article = Article(title=title, body=body)
    db.session.add(article)
    db.session.commit()

    return jsonify({"status": "ok", "data": serialize_article(article)}), 201


# --- GET /articles — List articles with optional tag filtering (design.md 2.2, 3.2) ---

@article_bp.route('/articles', methods=['GET'])
def list_articles():
    tag_name = request.args.get('tag')
    tag_id = request.args.get('tag_id')

    if tag_name:
        # tag parameter takes priority over tag_id (design.md 2.2)
        tag = Tag.query.filter_by(name=tag_name).first()
        if tag:
            articles = tag.articles.all()
        else:
            articles = []
    elif tag_id:
        tag = Tag.query.get(tag_id)
        if tag:
            articles = tag.articles.all()
        else:
            articles = []
    else:
        articles = Article.query.all()

    return jsonify({"status": "ok", "data": [serialize_article(a) for a in articles]}), 200


# --- GET /articles/<id> — Get single article (design.md 2.2) ---

@article_bp.route('/articles/<int:id>', methods=['GET'])
def get_article(id):
    article = Article.query.get(id)
    if not article:
        return jsonify({"status": "error", "message": "文章未找到"}), 404

    return jsonify({"status": "ok", "data": serialize_article(article)}), 200


# --- POST /articles/<id>/tags — Bind tags to article (design.md 2.2) ---

@article_bp.route('/articles/<int:id>/tags', methods=['POST'])
def bind_tags(id):
    article = Article.query.get(id)
    if not article:
        return jsonify({"status": "error", "message": "文章未找到"}), 404

    if not request.is_json:
        return jsonify({"status": "error", "message": "请求体必须是 JSON"}), 400

    data = request.get_json()
    tag_ids = data.get('tag_ids', [])

    if not tag_ids:
        # Empty array: idempotent, return 200 immediately (design.md 2.2)
        return jsonify({"status": "ok", "data": {"message": "Tags bound"}}), 200

    for tag_id in tag_ids:
        tag = Tag.query.get(tag_id)
        if not tag:
            return jsonify({"status": "error", "message": f"标签 ID {tag_id} 不存在"}), 400
        if tag not in article.tags:
            article.tags.append(tag)

    db.session.commit()
    return jsonify({"status": "ok", "data": {"message": "Tags bound"}}), 200


# --- GET /articles/<id>/tags — Get article's tags (design.md 2.2) ---

@article_bp.route('/articles/<int:id>/tags', methods=['GET'])
def get_article_tags(id):
    article = Article.query.get(id)
    if not article:
        return jsonify({"status": "error", "message": "文章未找到"}), 404

    return jsonify({"status": "ok", "data": [serialize_tag(t) for t in article.tags]}), 200


# --- DELETE /articles/<id>/tags/<tag_id> — Unbind tag from article (design.md 2.2) ---

@article_bp.route('/articles/<int:id>/tags/<int:tag_id>', methods=['DELETE'])
def unbind_tag(id, tag_id):
    article = Article.query.get(id)
    if not article:
        return jsonify({"status": "error", "message": "文章未找到"}), 404

    tag = Tag.query.get(tag_id)

    # Idempotent strategy (design.md 2.2):
    # Scene A: Tag doesn't exist -> still return 200
    # Scene B: Tag exists but not associated -> still return 200
    # Scene C: Tag exists and associated -> remove it
    if tag and tag in article.tags:
        article.tags.remove(tag)
        db.session.commit()

    return jsonify({"status": "ok", "data": {"message": "Tag unbound"}}), 200
