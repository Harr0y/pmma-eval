"""
T2 Blog -- Article Routes (Sample 1: Decorator-Based Error Handling Strategy)

Implementation approach:
- Custom @catch_db_errors decorator wraps all mutating routes for unified
  transaction safety (rollback on any exception).
- Centralized article serializer (article_to_dict) for consistent shaping.
- Article existence is resolved via a reusable _find_article() helper that
  returns (article, error_response) -- similar to the tag validation pattern
  but adapted for lookup rather than input validation.
- Tag-binding routes use bulk insert via association table with conflict
  handling through IntegrityError capture.
- Filtering supports both ?tag=<name> and ?tag_id=<id> via a single
  _build_filtered_query() factory, keeping list-article logic DRY.

Response contract:
  Success: {"status": "ok", "data": ...}
  Error:   {"status": "error", "message": "..."}
"""

from functools import wraps
from flask import Blueprint, request, jsonify
from sqlalchemy.exc import IntegrityError

from app import db
from models import Article, Tag, article_tags

article_bp = Blueprint('article_bp', __name__)


# ------------------------------------------------------------------ #
#  Decorator: catch_db_errors
# ------------------------------------------------------------------ #

def catch_db_errors(f):
    """Decorator: wrap a route handler in try/except with session rollback.

    If the wrapped function raises any exception, the DB session is rolled
    back and a generic 500 error is returned.  IntegrityError is mapped to
    409.  The decorator is intentionally kept simple -- it does NOT catch
    validation errors (those are returned as normal response tuples before
    any DB write happens).
    """
    @wraps(f)
    def wrapper(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except IntegrityError:
            db.session.rollback()
            return jsonify({"status": "error", "message": "Conflict"}), 409
        except Exception:
            db.session.rollback()
            return jsonify({"status": "error", "message": "Internal server error"}), 500
    return wrapper


# ------------------------------------------------------------------ #
#  Serializers
# ------------------------------------------------------------------ #

def article_to_dict(article):
    """Serialize an Article model instance to a plain dict."""
    return {"id": article.id, "title": article.title, "body": article.body}


def tag_to_dict(tag):
    """Serialize a Tag model instance to a plain dict."""
    return {"id": tag.id, "name": tag.name}


# ------------------------------------------------------------------ #
#  Lookup helper
# ------------------------------------------------------------------ #

def _find_article(article_id):
    """Fetch an article by ID.

    Returns:
        (Article, None) on success
        (None, response_tuple) when not found (404)
    """
    article = Article.query.get(article_id)
    if article is None:
        return None, (jsonify({"status": "error", "message": "Article not found"}), 404)
    return article, None


# ------------------------------------------------------------------ #
#  Validation helper
# ------------------------------------------------------------------ #

def _validate_article_payload(payload):
    """Validate the JSON payload for article creation.

    Returns:
        (dict, None) on success -- {'title': ..., 'body': ...}
        (None, response_tuple) on failure (400)
    """
    if not payload:
        return None, (jsonify({"status": "error", "message": "Request body must be JSON"}), 400)

    title = payload.get('title', '').strip() if payload.get('title') else ''
    body = payload.get('body', '').strip() if payload.get('body') else ''

    if not title or not body:
        missing = []
        if not title:
            missing.append('title')
        if not body:
            missing.append('body')
        msg = f"Missing required field(s): {', '.join(missing)}"
        return None, (jsonify({"status": "error", "message": msg}), 400)

    return {'title': title, 'body': body}, None


# ------------------------------------------------------------------ #
#  Filter query builder
# ------------------------------------------------------------------ #

def _build_filtered_query():
    """Build a base Article query, optionally filtered by tag.

    Supports two query parameters on GET /articles:
      ?tag=<name>   -- filter by tag name
      ?tag_id=<id>  -- filter by tag id

    Returns an SQLAlchemy query object.
    """
    tag_name = request.args.get('tag', '').strip()
    tag_id = request.args.get('tag_id', type=int)

    query = Article.query

    if tag_name:
        tag = Tag.query.filter_by(name=tag_name).first()
        if tag is None:
            # Return an impossible query so .all() yields []
            return Article.query.filter(Article.id == -1)
        query = query.filter(Article.tags.any(id=tag.id))

    if tag_id:
        query = query.filter(Article.tags.any(id=tag_id))

    return query


# ------------------------------------------------------------------ #
#  Routes -- CRUD
# ------------------------------------------------------------------ #

@article_bp.route('/articles', methods=['GET'])
def list_articles():
    """GET /articles -- list all articles, optionally filtered by tag."""
    query = _build_filtered_query()
    articles = query.order_by(Article.id).all()
    return jsonify({"status": "ok", "data": [article_to_dict(a) for a in articles]}), 200


@article_bp.route('/articles', methods=['POST'])
@catch_db_errors
def create_article():
    """POST /articles -- create a new article."""
    data, err = _validate_article_payload(request.get_json(silent=True))
    if err:
        return err

    article = Article(title=data['title'], body=data['body'])
    db.session.add(article)
    db.session.commit()

    return jsonify({"status": "ok", "data": article_to_dict(article)}), 201


@article_bp.route('/articles/<int:article_id>', methods=['GET'])
def get_article(article_id):
    """GET /articles/<id> -- retrieve a single article."""
    article, err = _find_article(article_id)
    if err:
        return err

    return jsonify({"status": "ok", "data": article_to_dict(article)}), 200


# ------------------------------------------------------------------ #
#  Routes -- Tag binding
# ------------------------------------------------------------------ #

@article_bp.route('/articles/<int:article_id>/tags', methods=['POST'])
@catch_db_errors
def bind_tags(article_id):
    """POST /articles/<id>/tags -- bind tags to an article.

    Request body: {"tag_ids": [1, 2, ...]}
    """
    article, err = _find_article(article_id)
    if err:
        return err

    payload = request.get_json(silent=True) or {}
    tag_ids = payload.get('tag_ids')

    if not tag_ids or not isinstance(tag_ids, list):
        return jsonify({"status": "error", "message": "tag_ids must be a non-empty list"}), 400

    # Verify all tag IDs exist before inserting
    existing_ids = set(
        t.id for t in Tag.query.filter(Tag.id.in_(tag_ids)).all()
    )
    missing = set(tag_ids) - existing_ids
    if missing:
        return jsonify({
            "status": "error",
            "message": f"Tag(s) not found: {', '.join(str(i) for i in sorted(missing))}"
        }), 400

    # Insert bindings via the association table (ignore duplicates via IntegrityError)
    for tid in tag_ids:
        db.session.execute(
            article_tags.insert().values(article_id=article_id, tag_id=tid)
        )

    db.session.commit()

    return jsonify({"status": "ok", "data": {"message": "Tags bound"}}), 200


@article_bp.route('/articles/<int:article_id>/tags', methods=['GET'])
def get_article_tags(article_id):
    """GET /articles/<id>/tags -- list all tags bound to an article."""
    article, err = _find_article(article_id)
    if err:
        return err

    tags = sorted(article.tags, key=lambda t: t.id)
    return jsonify({"status": "ok", "data": [tag_to_dict(t) for t in tags]}), 200


@article_bp.route('/articles/<int:article_id>/tags/<int:tag_id>', methods=['DELETE'])
@catch_db_errors
def unbind_tag(article_id, tag_id):
    """DELETE /articles/<id>/tags/<tag_id> -- remove a tag binding."""
    article, err = _find_article(article_id)
    if err:
        return err

    result = db.session.execute(
        article_tags.delete().where(
            (article_tags.c.article_id == article_id) &
            (article_tags.c.tag_id == tag_id)
        )
    )

    db.session.commit()

    return jsonify({"status": "ok", "data": {"message": "Tag unbound"}}), 200
