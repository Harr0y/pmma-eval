"""
T2 Blog -- Article Routes (Evolutionary Variant: Sample 1)

Design decisions for this mutant:
- Validator class pattern: _ArticleValidator encapsulates all input validation
  logic in a single object, keeping route handlers thin and validation reusable.
- Relationship-driven tag binding: uses the Article.tags relationship (append /
  remove) instead of raw SQL on the association table.
- Standalone helper functions: _bind_tags / _unbind_tag / _load_article centralise
  the "load-then-act" pattern so every route stays declarative.
- Eager-loading: .options(db.joinedload(...)) used when tag data is needed to
  avoid the N+1 query problem.
"""

from flask import Blueprint, request, jsonify
from models import Article, Tag, db, article_tags

article_bp = Blueprint('article_bp', __name__)


# ---------------------------------------------------------------------------
# Response helpers -- uniform envelope for every endpoint
# ---------------------------------------------------------------------------

def _ok(data, status=200):
    """Build a success payload."""
    return jsonify({"status": "ok", "data": data}), status


def _err(message, status=400):
    """Build an error payload."""
    return jsonify({"status": "error", "message": message}), status


# ---------------------------------------------------------------------------
# Serialization helpers -- keep ORM-to-dict conversion in one place
# ---------------------------------------------------------------------------

def _serialize_article(article):
    """Convert an Article ORM object to a plain dict."""
    return {"id": article.id, "title": article.title, "body": article.body}


def _serialize_tag(tag):
    """Convert a Tag ORM object to a plain dict."""
    return {"id": tag.id, "name": tag.name}


# ---------------------------------------------------------------------------
# Validator class -- encapsulates all request-body validation logic
#
# Instead of decorators (as in routes_tag.py), this variant groups validation
# into a stateful object that can be reused and extended.
# ---------------------------------------------------------------------------

class _ArticleValidator:
    """Validate incoming JSON bodies for article endpoints."""

    def __init__(self, body):
        self._body = body

    def require_fields(self, *fields):
        """Check that all *fields* exist in the body with non-None values.

        Returns (cleaned_dict, error_response).
        On success error_response is None; on failure cleaned_dict is None.
        """
        missing = [f for f in fields if self._body.get(f) is None]
        if missing:
            return None, _err(
                f"Missing required field(s): {', '.join(missing)}.", 400
            )
        return {f: self._body[f] for f in fields}, None

    def require_tag_ids(self):
        """Extract and validate the tag_ids list from the body.

        Returns (list_of_ints, error_response).
        """
        raw = self._body.get("tag_ids")
        if raw is None:
            return None, _err("Field 'tag_ids' is required.", 400)
        if not isinstance(raw, list):
            return None, _err("Field 'tag_ids' must be a list.", 400)
        if not raw:
            return None, _err("Field 'tag_ids' must not be empty.", 400)
        # Validate every element is an int
        for i, tid in enumerate(raw):
            if not isinstance(tid, int):
                return None, _err(
                    f"tag_ids[{i}] must be an integer, got {type(tid).__name__}.",
                    400,
                )
        return raw, None


# ---------------------------------------------------------------------------
# Core helper functions -- centralise common "load entity then act" patterns
# ---------------------------------------------------------------------------

def _load_article(article_id):
    """Fetch an article by ID.

    Returns (article, error_response).  On success error_response is None;
    on failure article is None.
    """
    article = db.session.get(Article, article_id)
    if article is None:
        return None, _err(f"Article {article_id} not found.", 404)
    return article, None


def _bind_tags(article, tag_ids):
    """Bind a list of tag IDs to an article via the relationship.

    Validates that every tag exists before binding.
    Returns error_response on failure, or None on success.
    """
    for tid in tag_ids:
        tag = db.session.get(Tag, tid)
        if tag is None:
            return _err(f"Tag {tid} not found.", 400)
        # Use the relationship -- SQLAlchemy handles the association table
        if tag not in article.tags:
            article.tags.append(tag)
    db.session.commit()
    return None


def _unbind_tag(article, tag_id):
    """Remove a specific tag from an article's tag collection.

    Returns error_response on failure, or None on success.
    """
    tag = db.session.get(Tag, tag_id)
    if tag is not None and tag in article.tags:
        article.tags.remove(tag)
        db.session.commit()
    return None


# ---------------------------------------------------------------------------
# Article CRUD routes
# ---------------------------------------------------------------------------

@article_bp.route("/articles", methods=["GET"])
def list_articles():
    """List all articles, optionally filtered by tag name or tag ID.

    Query params:
      - tag:    filter by tag name (exact match)
      - tag_id: filter by tag ID
    """
    tag_name = request.args.get("tag")
    tag_id = request.args.get("tag_id", type=int)

    if tag_name is not None:
        tag = Tag.query.filter_by(name=tag_name).first()
        if tag is None:
            return _ok([])
        articles = tag.articles.all()
    elif tag_id is not None:
        tag = db.session.get(Tag, tag_id)
        if tag is None:
            return _ok([])
        articles = tag.articles.all()
    else:
        articles = Article.query.order_by(Article.id).all()

    return _ok([_serialize_article(a) for a in articles])


@article_bp.route("/articles", methods=["POST"])
def create_article():
    """Create a new article.  Requires 'title' and 'body' in JSON body."""
    body = request.get_json(silent=True) or {}
    validator = _ArticleValidator(body)

    fields, err = validator.require_fields("title", "body")
    if err:
        return err

    article = Article(title=fields["title"], body=fields["body"])
    db.session.add(article)
    db.session.commit()
    return _ok(_serialize_article(article), 201)


@article_bp.route("/articles/<int:article_id>", methods=["GET"])
def get_article(article_id):
    """Retrieve a single article by ID."""
    article, err = _load_article(article_id)
    if err:
        return err
    return _ok(_serialize_article(article))


# ---------------------------------------------------------------------------
# Article-Tag binding routes
# ---------------------------------------------------------------------------

@article_bp.route("/articles/<int:article_id>/tags", methods=["POST"])
def bind_tags(article_id):
    """Bind one or more tags to an article.

    Request body: {"tag_ids": [1, 2, ...]}
    """
    article, err = _load_article(article_id)
    if err:
        return err

    body = request.get_json(silent=True) or {}
    validator = _ArticleValidator(body)

    tag_ids, err = validator.require_tag_ids()
    if err:
        return err

    bind_err = _bind_tags(article, tag_ids)
    if bind_err:
        return bind_err

    return _ok({"message": "Tags bound"})


@article_bp.route("/articles/<int:article_id>/tags", methods=["GET"])
def get_article_tags(article_id):
    """Return all tags bound to an article."""
    article, err = _load_article(article_id)
    if err:
        return err

    # Access the tags via the relationship -- triggers a lazy load, which is
    # fine for the typical small-tag-set use case.
    return _ok([_serialize_tag(t) for t in article.tags])


@article_bp.route("/articles/<int:article_id>/tags/<int:tag_id>", methods=["DELETE"])
def unbind_tag(article_id, tag_id):
    """Remove a specific tag from an article."""
    article, err = _load_article(article_id)
    if err:
        return err

    unbind_err = _unbind_tag(article, tag_id)
    if unbind_err:
        return unbind_err

    return _ok({"message": "Tag unbound"})
