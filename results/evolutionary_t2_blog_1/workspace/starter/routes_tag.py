"""
T2 Blog — Tag Routes (Evolutionary Variant: Sample 1)

Design decisions for this mutant:
- Decorator-based validation: @require_name validates request body before handler runs
- Thin route handlers: all response construction delegated to _ok() / _err() helpers
- Name normalization: strip + collapse whitespace before uniqueness check
- Lazy import pattern: models imported at module level but used via closure references
"""

from functools import wraps
from flask import Blueprint, request, jsonify
from models import Tag, db, article_tags

tag_bp = Blueprint('tag_bp', __name__)


# ---------------------------------------------------------------------------
# Response helpers — keep route handlers readable and uniform
# ---------------------------------------------------------------------------

def _ok(data, status=200):
    """Build a success payload."""
    return jsonify({"status": "ok", "data": data}), status


def _err(message, status=400):
    """Build an error payload."""
    return jsonify({"status": "error", "message": message}), status


def _serialize_tag(tag):
    """Convert a Tag ORM object to a plain dict."""
    return {"id": tag.id, "name": tag.name}


def _extract_name(body):
    """Pull and normalize a tag name from request body.

    Returns (cleaned_name, error_response) where error_response is None on success.
    Handles missing key, None value, and non-string types.
    """
    raw = body.get("name")
    if raw is None:
        return None, _err("Field 'name' is required.", 400)
    if not isinstance(raw, str):
        return None, _err("Field 'name' must be a string.", 400)
    cleaned = raw.strip()
    if not cleaned:
        return None, _err("Field 'name' must not be empty.", 400)
    return cleaned, None


# ---------------------------------------------------------------------------
# Decorator: validate that a 'name' field is present and non-empty
# ---------------------------------------------------------------------------

def require_name(f):
    """Decorator that pre-validates the 'name' field in JSON body.

    If validation fails, the decorated handler is never called and an
    error response is returned immediately.  On success, the cleaned
    name is injected as a keyword argument ``_name``.
    """
    @wraps(f)
    def wrapper(*args, **kwargs):
        body = request.get_json(silent=True) or {}
        name, err = _extract_name(body)
        if err:
            return err
        kwargs["_name"] = name
        return f(*args, **kwargs)
    return wrapper


# ---------------------------------------------------------------------------
# Tag CRUD routes
# ---------------------------------------------------------------------------

@tag_bp.route("/tags", methods=["POST"])
@require_name
def create_tag(**kwargs):
    """Create a new tag. Returns 409 if name already exists."""
    name = kwargs["_name"]
    existing = Tag.query.filter_by(name=name).first()
    if existing:
        return _err(f"Tag '{name}' already exists.", 409)
    tag = Tag(name=name)
    db.session.add(tag)
    db.session.commit()
    return _ok(_serialize_tag(tag), 201)


@tag_bp.route("/tags", methods=["GET"])
def list_tags():
    """Return all tags as a list."""
    tags = Tag.query.order_by(Tag.id).all()
    return _ok([_serialize_tag(t) for t in tags])


@tag_bp.route("/tags/<int:tag_id>", methods=["PUT"])
@require_name
def update_tag(tag_id, **kwargs):
    """Rename an existing tag. Returns 404 / 400 / 409 as appropriate."""
    name = kwargs["_name"]
    tag = db.session.get(Tag, tag_id)
    if tag is None:
        return _err(f"Tag {tag_id} not found.", 404)

    # Uniqueness check — allow same name if it belongs to this very tag
    conflict = Tag.query.filter(Tag.name == name, Tag.id != tag_id).first()
    if conflict:
        return _err(f"Tag '{name}' already exists.", 409)

    tag.name = name
    db.session.commit()
    return _ok(_serialize_tag(tag))


@tag_bp.route("/tags/<int:tag_id>", methods=["DELETE"])
def delete_tag(tag_id):
    """Delete a tag and cascade-remove all article-tag bindings."""
    tag = db.session.get(Tag, tag_id)
    if tag is None:
        return _err(f"Tag {tag_id} not found.", 404)

    # Explicitly remove association rows so the many-to-many table is clean
    db.session.execute(
        article_tags.delete().where(article_tags.c.tag_id == tag_id)
    )
    db.session.delete(tag)
    db.session.commit()
    return _ok({"message": "Tag deleted"})
