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


@tag_bp.route('/tags', methods=['POST'])
def create_tag():
    data = request.get_json()
    name = data.get('name')

    if not name:
        return jsonify({'status': 'error', 'message': 'Name is required'}), 400

    if Tag.query.filter_by(name=name).first() is not None:
        return jsonify({'status': 'error', 'message': 'Tag already exists'}), 409

    tag = Tag(name=name)
    db.session.add(tag)
    db.session.commit()

    return jsonify({'status': 'ok', 'data': {'id': tag.id, 'name': tag.name}}), 201


@tag_bp.route('/tags', methods=['GET'])
def list_tags():
    tags = Tag.query.all()
    data = [{'id': t.id, 'name': t.name} for t in tags]
    return jsonify({'status': 'ok', 'data': data})


@tag_bp.route('/tags/<int:tag_id>', methods=['PUT'])
def update_tag(tag_id):
    tag = Tag.query.get(tag_id)
    if tag is None:
        return jsonify({'status': 'error', 'message': 'Tag not found'}), 404

    data = request.get_json()
    name = data.get('name')

    if not name:
        return jsonify({'status': 'error', 'message': 'Name is required'}), 400

    existing = Tag.query.filter_by(name=name).first()
    if existing is not None and existing.id != tag_id:
        return jsonify({'status': 'error', 'message': 'Tag name already exists'}), 409

    tag.name = name
    db.session.commit()

    return jsonify({'status': 'ok', 'data': {'id': tag.id, 'name': tag.name}})


@tag_bp.route('/tags/<int:tag_id>', methods=['DELETE'])
def delete_tag(tag_id):
    tag = Tag.query.get(tag_id)
    if tag is None:
        return jsonify({'status': 'error', 'message': 'Tag not found'}), 404

    db.session.delete(tag)
    db.session.commit()

    return jsonify({'status': 'ok', 'data': {'message': 'Tag deleted'}})
