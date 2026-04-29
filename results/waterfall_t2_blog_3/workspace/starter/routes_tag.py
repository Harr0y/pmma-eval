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

from models import db, Tag, article_tags

tag_bp = Blueprint('tag_bp', __name__)


def ok_response(data, status_code=200):
    """Unified success response format."""
    return jsonify({"status": "ok", "data": data}), status_code


def error_response(message, status_code=400):
    """Unified error response format."""
    return jsonify({"status": "error", "message": message}), status_code


@tag_bp.route('/tags', methods=['POST'])
def create_tag():
    """Create a new tag.

    Design spec (3.7):
    - name is required (missing key or empty string -> 400)
    - Duplicate name -> 409
    - Success -> 201 with {id, name}
    """
    data = request.get_json()
    if not data or not data.get('name'):
        return error_response('Name is required', 400)

    name = data['name']
    if not isinstance(name, str) or not name.strip():
        return error_response('Name is required', 400)

    existing = Tag.query.filter_by(name=name).first()
    if existing:
        return error_response('Tag already exists', 409)

    tag = Tag(name=name)
    db.session.add(tag)
    db.session.commit()

    return ok_response({'id': tag.id, 'name': tag.name}, 201)


@tag_bp.route('/tags', methods=['GET'])
def list_tags():
    """List all tags.

    Design spec (3.8):
    - Returns 200 with list of {id, name} dicts
    - Empty list if no tags exist
    """
    tags = Tag.query.all()
    return ok_response([{'id': t.id, 'name': t.name} for t in tags])


@tag_bp.route('/tags/<int:tag_id>', methods=['PUT'])
def update_tag(tag_id):
    """Update a tag's name.

    Design spec (3.8):
    - Tag not found -> 404
    - name missing -> 400
    - New name duplicates another tag (excluding self) -> 409
    - Success -> 200 with {id, name}
    """
    tag = Tag.query.get(tag_id)
    if not tag:
        return error_response('Tag not found', 404)

    data = request.get_json()
    if not data or not data.get('name'):
        return error_response('Name is required', 400)

    new_name = data['name']
    existing = Tag.query.filter(Tag.name == new_name, Tag.id != tag_id).first()
    if existing:
        return error_response('Tag name already exists', 409)

    tag.name = new_name
    db.session.commit()

    return ok_response({'id': tag.id, 'name': tag.name})


@tag_bp.route('/tags/<int:tag_id>', methods=['DELETE'])
def delete_tag(tag_id):
    """Delete a tag and cascade-remove all article-tag associations.

    Design spec (3.9):
    - Tag not found -> 404
    - Explicitly delete article_tags associations via db.session.execute()
    - Then delete the tag itself
    - Success -> 200 with {message: "Tag deleted"}
    """
    tag = Tag.query.get(tag_id)
    if not tag:
        return error_response('Tag not found', 404)

    # Explicitly remove all article-tag associations for this tag
    db.session.execute(
        article_tags.delete().where(article_tags.c.tag_id == tag_id)
    )
    db.session.delete(tag)
    db.session.commit()

    return ok_response({'message': 'Tag deleted'})
