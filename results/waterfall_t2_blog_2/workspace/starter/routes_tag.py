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
from app import db
from models import Tag, article_tags

tag_bp = Blueprint('tag_bp', __name__)


@tag_bp.route('/tags', methods=['POST'])
def create_tag():
    """Create a new tag.

    Validates that 'name' is present and non-empty, checks uniqueness.
    Returns 201 on success, 400 if name missing/empty, 409 if duplicate.
    """
    data = request.get_json()
    # Validate: name must exist and be non-empty
    if not data or not data.get('name'):
        return jsonify({"status": "error", "message": "name is required"}), 400
    # Validate: name uniqueness
    existing = Tag.query.filter_by(name=data['name']).first()
    if existing:
        return jsonify({"status": "error", "message": "Tag already exists"}), 409
    tag = Tag(name=data['name'])
    db.session.add(tag)
    db.session.commit()
    return jsonify({"status": "ok", "data": {"id": tag.id, "name": tag.name}}), 201


@tag_bp.route('/tags', methods=['GET'])
def list_tags():
    """List all tags.

    Returns 200 with a list of all tags.
    """
    tags = Tag.query.all()
    return jsonify({"status": "ok", "data": [{"id": t.id, "name": t.name} for t in tags]}), 200


@tag_bp.route('/tags/<int:id>', methods=['PUT'])
def update_tag(id):
    """Update a tag's name.

    Validates tag existence, name presence, and uniqueness (excluding self).
    Returns 200 on success, 404 if not found, 400 if name missing, 409 if duplicate.
    """
    tag = Tag.query.get(id)
    if not tag:
        return jsonify({"status": "error", "message": "Tag not found"}), 404
    data = request.get_json()
    if not data or not data.get('name'):
        return jsonify({"status": "error", "message": "name is required"}), 400
    existing = Tag.query.filter_by(name=data['name']).first()
    if existing and existing.id != id:
        return jsonify({"status": "error", "message": "Tag name already exists"}), 409
    tag.name = data['name']
    db.session.commit()
    return jsonify({"status": "ok", "data": {"id": tag.id, "name": tag.name}}), 200


@tag_bp.route('/tags/<int:id>', methods=['DELETE'])
def delete_tag(id):
    """Delete a tag and cascade-remove all article-tag associations.

    Manually clears article_tags associations before deleting the tag,
    since SQLite CASCADE requires explicit PRAGMA configuration.
    Returns 200 on success, 404 if not found.
    """
    tag = Tag.query.get(id)
    if not tag:
        return jsonify({"status": "error", "message": "Tag not found"}), 404
    # Manually clear associations (avoid relying on SQLite CASCADE)
    db.session.execute(article_tags.delete().where(article_tags.c.tag_id == id))
    db.session.delete(tag)
    db.session.commit()
    return jsonify({"status": "ok", "data": {"message": "Tag deleted"}}), 200
