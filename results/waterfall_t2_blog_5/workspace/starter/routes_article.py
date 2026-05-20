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

from app import db
from models import Article, Tag

article_bp = Blueprint('article_bp', __name__)


def article_to_dict(article):
    """Serialize an Article object to a dictionary."""
    return {"id": article.id, "title": article.title, "body": article.body}


def tag_to_dict(tag):
    """Serialize a Tag object to a dictionary."""
    return {"id": tag.id, "name": tag.name}


# ============================================================
# POST /articles — 创建文章
# Design: 3.2 Section 1, FR-ART-01
# ============================================================

@article_bp.route('/articles', methods=['POST'])
def create_article():
    """Create a new article.

    Request body: {"title": "str", "body": "str"}
    - 400 if title or body is missing or empty/non-string
    - 201 on success
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"status": "error", "message": "Request body must be JSON"}), 400

    title = data.get('title')
    body = data.get('body')

    if not title or not isinstance(title, str) or not title.strip():
        return jsonify({"status": "error", "message": "title is required"}), 400
    if not body or not isinstance(body, str) or not body.strip():
        return jsonify({"status": "error", "message": "body is required"}), 400

    article = Article(title=title.strip(), body=body.strip())
    db.session.add(article)
    db.session.commit()

    return jsonify({"status": "ok", "data": article_to_dict(article)}), 201


# ============================================================
# GET /articles — 列出所有文章（支持标签筛选）
# Design: 3.2 Section 2, FR-ART-02
# ============================================================

@article_bp.route('/articles', methods=['GET'])
def list_articles():
    """List all articles, optionally filtered by tag.

    Query params:
    - tag_id: filter by tag ID (takes priority)
    - tag: filter by tag name (fallback if tag_id not provided)
    - No params: return all articles
    """
    tag_id = request.args.get('tag_id')
    tag_name = request.args.get('tag')

    if tag_id:
        try:
            tag_id_int = int(tag_id)
        except (ValueError, TypeError):
            return jsonify({"status": "ok", "data": []}), 200
        tag = db.session.get(Tag, tag_id_int)
        articles = tag.articles.all() if tag else []
    elif tag_name:
        tag = Tag.query.filter_by(name=tag_name).first()
        articles = tag.articles.all() if tag else []
    else:
        articles = Article.query.all()

    return jsonify({"status": "ok", "data": [article_to_dict(a) for a in articles]}), 200


# ============================================================
# GET /articles/<id> — 获取单篇文章
# Design: 3.2 Section 3, FR-ART-03
# ============================================================

@article_bp.route('/articles/<int:id>', methods=['GET'])
def get_article(id):
    """Get a single article by ID.

    - 404 if article not found
    - 200 on success
    """
    article = db.session.get(Article, id)
    if not article:
        return jsonify({"status": "error", "message": "Article not found"}), 404

    return jsonify({"status": "ok", "data": article_to_dict(article)}), 200


# ============================================================
# POST /articles/<id>/tags — 为文章绑定标签
# Design: 3.2 Section 4, FR-ART-04
# ============================================================

@article_bp.route('/articles/<int:id>/tags', methods=['POST'])
def bind_tags(id):
    """Bind tags to an article.

    Request body: {"tag_ids": [int, ...]}
    - 404 if article not found
    - 400 if any tag_id in tag_ids does not exist
    - 200 on success (idempotent: already-bound tags are silently skipped)
    """
    article = db.session.get(Article, id)
    if not article:
        return jsonify({"status": "error", "message": "Article not found"}), 404

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"status": "error", "message": "Request body must be JSON"}), 400

    tag_ids = data.get('tag_ids', [])
    if not isinstance(tag_ids, list):
        return jsonify({"status": "error", "message": "tag_ids must be a list"}), 400

    tags = []
    for tid in tag_ids:
        tag = db.session.get(Tag, tid)
        if not tag:
            return jsonify({"status": "error", "message": f"Tag {tid} not found"}), 400
        if tag not in article.tags:  # idempotent: skip already-bound tags
            tags.append(tag)

    if tags:
        article.tags.extend(tags)
        db.session.commit()

    return jsonify({"status": "ok", "data": {"message": "Tags bound"}}), 200


# ============================================================
# GET /articles/<id>/tags — 获取文章的所有标签
# Design: 3.2 Section 5, FR-ART-05
# ============================================================

@article_bp.route('/articles/<int:id>/tags', methods=['GET'])
def get_article_tags(id):
    """Get all tags bound to an article.

    - 404 if article not found
    - 200 on success (returns list of tags, possibly empty)
    """
    article = db.session.get(Article, id)
    if not article:
        return jsonify({"status": "error", "message": "Article not found"}), 404

    return jsonify({"status": "ok", "data": [tag_to_dict(t) for t in article.tags]}), 200


# ============================================================
# DELETE /articles/<id>/tags/<tag_id> — 解除关联
# Design: 3.2 Section 6, FR-ART-06
# ============================================================

@article_bp.route('/articles/<int:id>/tags/<int:tag_id>', methods=['DELETE'])
def unbind_tag(id, tag_id):
    """Unbind a tag from an article.

    - 404 if article not found
    - 200 on success even if the tag was not bound to the article
    """
    article = db.session.get(Article, id)
    if not article:
        return jsonify({"status": "error", "message": "Article not found"}), 404

    tag = db.session.get(Tag, tag_id)
    if tag and tag in article.tags:
        article.tags.remove(tag)
        db.session.commit()

    return jsonify({"status": "ok", "data": {"message": "Tag unbound"}}), 200
