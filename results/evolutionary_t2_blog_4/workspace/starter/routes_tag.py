"""
T2 Blog -- Tag Routes (Sample 2: Functional decomposition + SQLAlchemy 2.0 select)

Design decisions for this variant:
- Each route handler delegates to a pure helper function that encapsulates
  the business logic, keeping route handlers thin and focused on HTTP concerns.
- Uses SQLAlchemy 2.0-style `select()` / `scalars()` queries instead of the
  legacy `Model.query` ORM API, providing a different query paradigm.
- Tag deletion uses raw SQL DELETE on the association table via
  `db.session.execute(delete(...))` for explicit cascade control, rather than
  relying on SQLAlchemy relationship cascade configuration.
- Validation is performed by a dedicated `_extract_name` helper that returns
  a tuple of (error_response, name) so the route can short-circuit early.
- A single `_serialize_tag` helper centralizes the tag-to-dict conversion,
  ensuring consistent response shapes across all endpoints.
"""

from flask import Blueprint, request, jsonify
from sqlalchemy import select, delete as sa_delete

from app import db
from models import Tag, article_tags

tag_bp = Blueprint('tag_bp', __name__)


# ---------------------------------------------------------------------------
# Serialization helper
# ---------------------------------------------------------------------------

def _serialize_tag(tag: Tag) -> dict:
    """Convert a Tag ORM object to a plain dictionary."""
    return {"id": tag.id, "name": tag.name}


# ---------------------------------------------------------------------------
# Input validation helper
# ---------------------------------------------------------------------------

def _extract_name(payload: dict):
    """
    Extract and validate the 'name' field from a JSON payload.

    Returns:
        (error_jsonify, None)   -- if validation fails (caller should return this)
        (None, name)            -- if validation succeeds
    """
    if not payload or not payload.get("name"):
        return (jsonify({"status": "error", "message": "name is required"}), 400), None

    name = payload["name"]
    if not isinstance(name, str) or not name.strip():
        return (jsonify({"status": "error", "message": "name must be a non-empty string"}), 400), None

    return None, name.strip()


# ---------------------------------------------------------------------------
# Business logic helpers
# ---------------------------------------------------------------------------

def _create_tag(name: str):
    """Create a new tag. Returns (response_tuple, http_status_code)."""
    # Check uniqueness using select() style query
    existing = db.session.scalars(
        select(Tag).where(Tag.name == name)
    ).first()

    if existing is not None:
        return jsonify({"status": "error", "message": f"Tag '{name}' already exists"}), 409

    tag = Tag(name=name)
    db.session.add(tag)
    db.session.commit()

    return jsonify({"status": "ok", "data": _serialize_tag(tag)}), 201


def _list_tags():
    """List all tags. Returns (response_tuple, http_status_code)."""
    tags = db.session.scalars(select(Tag).order_by(Tag.id)).all()
    return jsonify({"status": "ok", "data": [_serialize_tag(t) for t in tags]}), 200


def _update_tag(tag_id: int, name: str):
    """Update a tag's name. Returns (response_tuple, http_status_code)."""
    tag = db.session.scalars(
        select(Tag).where(Tag.id == tag_id)
    ).first()

    if tag is None:
        return jsonify({"status": "error", "message": "Tag not found"}), 404

    # Check name uniqueness (excluding the current tag)
    conflict = db.session.scalars(
        select(Tag).where(Tag.name == name, Tag.id != tag_id)
    ).first()

    if conflict is not None:
        return jsonify({"status": "error", "message": f"Tag '{name}' already exists"}), 409

    tag.name = name
    db.session.commit()

    return jsonify({"status": "ok", "data": _serialize_tag(tag)}), 200


def _delete_tag(tag_id: int):
    """Delete a tag and all its article associations. Returns (response_tuple, http_status_code)."""
    tag = db.session.scalars(
        select(Tag).where(Tag.id == tag_id)
    ).first()

    if tag is None:
        return jsonify({"status": "error", "message": "Tag not found"}), 404

    # Explicitly remove all association rows first (cascade control)
    db.session.execute(
        sa_delete(article_tags).where(article_tags.c.tag_id == tag_id)
    )

    # Then delete the tag itself
    db.session.delete(tag)
    db.session.commit()

    return jsonify({"status": "ok", "data": {"message": "Tag deleted"}}), 200


# ---------------------------------------------------------------------------
# Route handlers (thin -- delegate to helpers)
# ---------------------------------------------------------------------------

@tag_bp.route("/tags", methods=["POST"])
def create_tag():
    """POST /tags -- Create a new tag."""
    err, name = _extract_name(request.get_json(silent=True) or {})
    if err:
        return err
    return _create_tag(name)


@tag_bp.route("/tags", methods=["GET"])
def list_tags():
    """GET /tags -- List all tags."""
    return _list_tags()


@tag_bp.route("/tags/<int:tag_id>", methods=["PUT"])
def update_tag(tag_id):
    """PUT /tags/<id> -- Update a tag's name."""
    err, name = _extract_name(request.get_json(silent=True) or {})
    if err:
        return err
    return _update_tag(tag_id, name)


@tag_bp.route("/tags/<int:tag_id>", methods=["DELETE"])
def delete_tag(tag_id):
    """DELETE /tags/<id> -- Delete a tag and its article associations."""
    return _delete_tag(tag_id)
