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
from models import Tag

tag_bp = Blueprint('tag_bp', __name__)


def tag_to_dict(tag):
    """Serialize a Tag object to a dictionary."""
    return {"id": tag.id, "name": tag.name}


@tag_bp.route('/tags', methods=['POST'])
def create_tag():
    """Create a new tag.

    Request body: {"name": "str"}
    - 400 if name is missing or empty/whitespace-only
    - 409 if a tag with the same name already exists
    - 201 on success
    """
    data = request.get_json(silent=True)
    name = data.get('name') if data else None
    if not name or not isinstance(name, str) or not name.strip():
        return jsonify({"status": "error", "message": "Tag name is required and must not be empty"}), 400
    name = name.strip()

    if Tag.query.filter_by(name=name).first():
        return jsonify({"status": "error", "message": "Tag name already exists"}), 409

    tag = Tag(name=name)
    db.session.add(tag)
    db.session.commit()

    return jsonify({"status": "ok", "data": tag_to_dict(tag)}), 201


@tag_bp.route('/tags', methods=['GET'])
def list_tags():
    """List all tags.

    Returns a list of all tags, or an empty list if none exist.
    """
    tags = Tag.query.all()
    return jsonify({"status": "ok", "data": [tag_to_dict(t) for t in tags]}), 200


@tag_bp.route('/tags/<int:id>', methods=['PUT'])
def update_tag(id):
    """Update a tag's name.

    Request body: {"name": "str"}
    - 404 if tag with given id does not exist
    - 400 if name is missing or empty/whitespace-only
    - 409 if new name conflicts with another existing tag (excluding self)
    - 200 on success
    """
    tag = db.session.get(Tag, id)
    if not tag:
        return jsonify({"status": "error", "message": "Tag not found"}), 404

    data = request.get_json(silent=True)
    name = data.get('name') if data else None
    if not name or not isinstance(name, str) or not name.strip():
        return jsonify({"status": "error", "message": "Tag name is required and must not be empty"}), 400
    name = name.strip()

    duplicate = Tag.query.filter(Tag.name == name, Tag.id != id).first()
    if duplicate:
        return jsonify({"status": "error", "message": "Tag name already exists"}), 409

    tag.name = name
    db.session.commit()

    return jsonify({"status": "ok", "data": tag_to_dict(tag)}), 200


@tag_bp.route('/tags/<int:id>', methods=['DELETE'])
def delete_tag(id):
    """Delete a tag.

    - 404 if tag with given id does not exist
    - 200 on success; cascade deletes article_tags associations automatically
    """
    tag = db.session.get(Tag, id)
    if not tag:
        return jsonify({"status": "error", "message": "Tag not found"}), 404

    db.session.delete(tag)
    db.session.commit()

    return jsonify({"status": "ok", "data": {"message": "Tag deleted"}}), 200
