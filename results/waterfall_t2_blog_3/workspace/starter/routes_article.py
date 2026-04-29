"""
T2 Blog -- Article Routes

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

from models import db, Article, Tag

article_bp = Blueprint('article_bp', __name__)


def ok_response(data, status_code=200):
    """Unified success response format.

    Design spec (3.10):
    {"status": "ok", "data": ...}
    """
    return jsonify({"status": "ok", "data": data}), status_code


def error_response(message, status_code=400):
    """Unified error response format.

    Design spec (3.10):
    {"status": "error", "message": "error description"}
    """
    return jsonify({"status": "error", "message": message}), status_code


@article_bp.route('/articles', methods=['POST'])
def create_article():
    """Create a new article.

    Design spec (3.1):
    - title and body are both required; missing either -> 400
    - request.get_json() may be None (non-JSON request), must guard
    - Success -> 201 with {id, title, body}
    """
    data = request.get_json()
    if not data or 'title' not in data or 'body' not in data:
        return error_response('Title and body are required', 400)

    article = Article(title=data['title'], body=data['body'])
    db.session.add(article)
    db.session.commit()

    return ok_response({
        'id': article.id,
        'title': article.title,
        'body': article.body
    }, 201)


@article_bp.route('/articles/<int:article_id>', methods=['GET'])
def get_article(article_id):
    """Get a single article by ID.

    Design spec (3.2):
    - Article not found -> 404
    - <int:article_id> ensures ID is integer
    - Success -> 200 with {id, title, body}
    """
    article = Article.query.get(article_id)
    if not article:
        return error_response('Article not found', 404)

    return ok_response({
        'id': article.id,
        'title': article.title,
        'body': article.body
    })


@article_bp.route('/articles', methods=['GET'])
def list_articles():
    """List all articles with optional tag filtering.

    Design spec (3.3):
    - Query params: tag (by name), tag_id (by ID)
    - tag_id comes as str from request.args.get(), needs int() conversion
    - No match -> empty list [], still HTTP 200
    - tag.articles uses lazy='dynamic', needs .all() to get list
    """
    tag_name = request.args.get('tag')
    tag_id_str = request.args.get('tag_id')

    if tag_name:
        tag = Tag.query.filter_by(name=tag_name).first()
        articles = tag.articles.all() if tag else []
    elif tag_id_str:
        tag = Tag.query.get(int(tag_id_str))
        articles = tag.articles.all() if tag else []
    else:
        articles = Article.query.all()

    return ok_response([{
        'id': a.id,
        'title': a.title,
        'body': a.body
    } for a in articles])


@article_bp.route('/articles/<int:article_id>/tags', methods=['POST'])
def bind_tags(article_id):
    """Bind one or more tags to an article.

    Design spec (3.4):
    - Article not found -> 404
    - Validate each tag_id exists; any missing -> 400
    - Idempotent: already-bound tags are skipped
    - Success -> 200 with {message: "Tags bound"}
    """
    article = Article.query.get(article_id)
    if not article:
        return error_response('Article not found', 404)

    data = request.get_json()
    tag_ids = data.get('tag_ids', []) if data else []
    for tid in tag_ids:
        tag = Tag.query.get(tid)
        if not tag:
            return error_response('Tag not found', 400)
        if tag not in article.tags:
            article.tags.append(tag)

    db.session.commit()
    return ok_response({'message': 'Tags bound'})


@article_bp.route('/articles/<int:article_id>/tags', methods=['GET'])
def get_article_tags(article_id):
    """Get all tags for an article.

    Design spec (3.5):
    - Article not found -> 404
    - Success -> 200 with list of {id, name}
    """
    article = Article.query.get(article_id)
    if not article:
        return error_response('Article not found', 404)

    return ok_response([{'id': t.id, 'name': t.name} for t in article.tags])


@article_bp.route('/articles/<int:article_id>/tags/<int:tag_id>', methods=['DELETE'])
def unbind_tag(article_id, tag_id):
    """Unbind a tag from an article.

    Design spec (3.6):
    - Article not found -> 404
    - Idempotent: unbinding a tag that is not bound does not error
    - Success -> 200 with {message: "Tag unbound"}
    """
    article = Article.query.get(article_id)
    if not article:
        return error_response('Article not found', 404)

    tag = Tag.query.get(tag_id)
    if tag and tag in article.tags:
        article.tags.remove(tag)

    db.session.commit()
    return ok_response({'message': 'Tag unbound'})
