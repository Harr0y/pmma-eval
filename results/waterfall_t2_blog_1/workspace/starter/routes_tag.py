"""
T2 Blog — Tag Routes

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
from models import Tag, db, article_tags

tag_bp = Blueprint('tag_bp', __name__)


@tag_bp.route('/tags', methods=['POST'])
def create_tag():
    """Create a new tag. Requires 'name' field. Returns 201 on success."""
    data = request.get_json()
    # Validate: name must exist and be a non-empty, non-whitespace string
    name = data.get('name') if data else None
    if not name or not name.strip():
        return jsonify({"status": "error", "message": "Name is required"}), 400
    # Check uniqueness
    existing = Tag.query.filter_by(name=name).first()
    if existing:
        return jsonify({"status": "error", "message": "Tag already exists"}), 409
    # Create tag
    tag = Tag(name=name)
    db.session.add(tag)
    db.session.commit()
    return jsonify({"status": "ok", "data": {"id": tag.id, "name": tag.name}}), 201


@tag_bp.route('/tags', methods=['GET'])
def list_tags():
    """List all tags."""
    tags = Tag.query.all()
    return jsonify({"status": "ok", "data": [{"id": t.id, "name": t.name} for t in tags]}), 200


@tag_bp.route('/tags/<int:id>', methods=['PUT'])
def update_tag(id):
    """Update a tag's name. Returns 200 on success."""
    data = request.get_json()
    # Validate: name must exist and be a non-empty, non-whitespace string
    name = data.get('name') if data else None
    if not name or not name.strip():
        return jsonify({"status": "error", "message": "Name is required"}), 400
    # Find tag
    tag = Tag.query.get(id)
    if not tag:
        return jsonify({"status": "error", "message": "Tag not found"}), 404
    # Check uniqueness (exclude self)
    existing = Tag.query.filter(Tag.name == name, Tag.id != id).first()
    if existing:
        return jsonify({"status": "error", "message": "Tag name already exists"}), 409
    tag.name = name
    db.session.commit()
    return jsonify({"status": "ok", "data": {"id": tag.id, "name": tag.name}}), 200


@tag_bp.route('/tags/<int:id>', methods=['DELETE'])
def delete_tag(id):
    """Delete a tag and manually clean up article_tags associations."""
    tag = Tag.query.get(id)
    if not tag:
        return jsonify({"status": "error", "message": "Tag not found"}), 404
    # Clean up association records (SQLite does not enforce FK constraints)
    db.session.execute(article_tags.delete().where(article_tags.c.tag_id == id))
    db.session.delete(tag)
    db.session.commit()
    return jsonify({"status": "ok", "data": {"message": "Tag deleted"}}), 200
