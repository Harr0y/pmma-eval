"""
T2 Blog - Tag Routes (Sample 2: Validation-Helper + Try/Except Strategy)

Implementation approach:
- Centralized validation helper (validate_name) reused across routes
- All DB mutations wrapped in try/except with rollback on failure
- IntegrityError-based duplicate detection (no pre-query needed)
- Explicit tag serializer (tag_to_dict) for consistent response shaping
"""

from flask import Blueprint, request, jsonify
from sqlalchemy.exc import IntegrityError

from app import db
from models import Tag, article_tags

tag_bp = Blueprint('tag_bp', __name__)


def validate_name(payload):
    """Extract and validate the 'name' field from a JSON payload.

    Returns:
        (str, None) on success - the validated name string
        (None, response_tuple) on failure - a Flask error response

    This helper is called by create and update routes to ensure
    consistent input validation logic.
    """
    if not payload or 'name' not in payload:
        return None, (jsonify({"status": "error", "message": "Missing required field: name"}), 400)

    name = payload.get('name', '').strip()
    if not name:
        return None, (jsonify({"status": "error", "message": "Missing required field: name"}), 400)

    return name, None


def tag_to_dict(tag):
    """Serialize a Tag model instance to a plain dict."""
    return {"id": tag.id, "name": tag.name}


@tag_bp.route('/tags', methods=['POST'])
def create_tag():
    name, err = validate_name(request.get_json(silent=True))
    if err:
        return err

    tag = Tag(name=name)
    db.session.add(tag)

    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"status": "error", "message": "Tag already exists"}), 409

    return jsonify({"status": "ok", "data": tag_to_dict(tag)}), 201


@tag_bp.route('/tags', methods=['GET'])
def list_tags():
    tags = Tag.query.order_by(Tag.id).all()
    return jsonify({"status": "ok", "data": [tag_to_dict(t) for t in tags]}), 200


@tag_bp.route('/tags/<int:tag_id>', methods=['PUT'])
def update_tag(tag_id):
    tag = Tag.query.get(tag_id)
    if tag is None:
        return jsonify({"status": "error", "message": "Tag not found"}), 404

    name, err = validate_name(request.get_json(silent=True))
    if err:
        return err

    tag.name = name

    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"status": "error", "message": "Tag already exists"}), 409

    return jsonify({"status": "ok", "data": tag_to_dict(tag)}), 200


@tag_bp.route('/tags/<int:tag_id>', methods=['DELETE'])
def delete_tag(tag_id):
    tag = Tag.query.get(tag_id)
    if tag is None:
        return jsonify({"status": "error", "message": "Tag not found"}), 404

    try:
        # Cascade-delete all article-tag bindings via the association table
        db.session.execute(
            article_tags.delete().where(article_tags.c.tag_id == tag_id)
        )
        db.session.delete(tag)
        db.session.commit()
    except Exception:
        db.session.rollback()
        return jsonify({"status": "error", "message": "Failed to delete tag"}), 500

    return jsonify({"status": "ok", "data": {"message": "Tag deleted"}}), 200
