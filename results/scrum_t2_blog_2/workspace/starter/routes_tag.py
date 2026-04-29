"""
T2 Blog -- Tag Routes

Implement tag CRUD routes.
Register as a Flask Blueprint named 'tag_bp'.

Requirements:
- POST /tags -> Create tag
  Request: {"name": str}
  Response: {"status": "ok", "data": {"id": int, "name": str}}
  Errors: 400 if name missing/empty, 409 if name already exists

- GET /tags -> List all tags
  Response: {"status": "ok", "data": [{"id": int, "name": str}, ...]}

- PUT /tags/<id> -> Update tag name
  Request: {"name": str}
  Response: {"status": "ok", "data": {"id": int, "name": str}}
  Errors: 404 if not found, 400 if name missing, 409 if duplicate name

- DELETE /tags/<id> -> Delete tag (also removes all article-tag associations)
  Response: {"status": "ok", "data": {"message": "Tag deleted"}}
  Errors: 404 if not found

IMPORTANT: Deleting a tag should cascade and remove all article-tag bindings
in the article_tags association table. This is used by routes_article.py.
"""

from flask import Blueprint, request, jsonify
from app import db
from models import Tag

tag_bp = Blueprint('tag_bp', __name__)


@tag_bp.route('/tags', methods=['POST'])
def create_tag():
    """Create a new tag. Requires 'name' in JSON body."""
    data = request.get_json(silent=True) or {}
    name = data.get('name')
    if not name or not str(name).strip():
        return jsonify({"status": "error", "message": "name is required"}), 400

    if Tag.query.filter_by(name=name).first():
        return jsonify({"status": "error", "message": "Tag already exists"}), 409

    tag = Tag(name=name)
    db.session.add(tag)
    db.session.commit()
    return jsonify({"status": "ok", "data": {"id": tag.id, "name": tag.name}}), 201


@tag_bp.route('/tags', methods=['GET'])
def list_tags():
    """List all tags."""
    tags = Tag.query.all()
    return jsonify({"status": "ok", "data": [{"id": t.id, "name": t.name} for t in tags]}), 200


@tag_bp.route('/tags/<int:tag_id>', methods=['PUT'])
def update_tag(tag_id):
    """Update a tag's name by ID."""
    tag = Tag.query.get(tag_id)
    if not tag:
        return jsonify({"status": "error", "message": "Tag not found"}), 404

    data = request.get_json(silent=True) or {}
    name = data.get('name')
    if not name or not str(name).strip():
        return jsonify({"status": "error", "message": "name is required"}), 400

    existing = Tag.query.filter_by(name=name).first()
    if existing and existing.id != tag_id:
        return jsonify({"status": "error", "message": "Tag already exists"}), 409

    tag.name = name
    db.session.commit()
    return jsonify({"status": "ok", "data": {"id": tag.id, "name": tag.name}}), 200


@tag_bp.route('/tags/<int:tag_id>', methods=['DELETE'])
def delete_tag(tag_id):
    """Delete a tag and cascade-remove all article-tag associations."""
    tag = Tag.query.get(tag_id)
    if not tag:
        return jsonify({"status": "error", "message": "Tag not found"}), 404

    db.session.delete(tag)
    db.session.commit()
    return jsonify({"status": "ok", "data": {"message": "Tag deleted"}}), 200
