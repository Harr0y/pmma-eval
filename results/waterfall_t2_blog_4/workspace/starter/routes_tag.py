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
from models import Tag, db

tag_bp = Blueprint('tag_bp', __name__)


def _serialize_tag(tag):
    """Serialize a Tag object to dict (design.md section 6)."""
    return {"id": tag.id, "name": tag.name}


@tag_bp.route('/tags', methods=['POST'])
def create_tag():
    """POST /tags — Create a new tag.

    design.md 2.1:
      1. Validate request body is JSON
      2. Extract name; if missing or empty string -> 400
      3. Check name uniqueness -> if exists, 409
      4. Create Tag, db.session.add + commit
    Returns 201 on success.
    """
    # Step 1: Validate JSON body (design.md section 4)
    data = request.get_json(silent=True)
    if data is None:
        return jsonify({"status": "error", "message": "请求体必须是 JSON"}), 400

    # Step 2: Extract and validate name (design.md 2.1)
    name = data.get('name')
    if not name or not isinstance(name, str) or not name.strip():
        return jsonify({"status": "error", "message": "name is required and must be a non-empty string"}), 400

    name = name.strip()

    # Step 3: Uniqueness check (design.md 3.1)
    existing = Tag.query.filter_by(name=name).first()
    if existing:
        return jsonify({"status": "error", "message": "名称已存在"}), 409

    # Step 4: Create and persist (design.md 2.1)
    tag = Tag(name=name)
    db.session.add(tag)
    db.session.commit()

    return jsonify({"status": "ok", "data": _serialize_tag(tag)}), 201


@tag_bp.route('/tags', methods=['GET'])
def list_tags():
    """GET /tags — List all tags.

    design.md 2.1:
      1. Tag.query.all()
      2. Serialize to [{"id": int, "name": str}, ...]
    Returns 200 on success.
    """
    tags = Tag.query.all()
    return jsonify({"status": "ok", "data": [_serialize_tag(t) for t in tags]}), 200


@tag_bp.route('/tags/<int:id>', methods=['PUT'])
def update_tag(id):
    """PUT /tags/<id> — Update a tag's name.

    design.md 2.1:
      1. Validate request body is JSON
      2. Extract name; if missing or empty string -> 400
      3. Find Tag.query.get(id); if not found -> 404
      4. Check new name uniqueness excluding self (design.md 3.1);
         if same as current name, treat as no-op (no 409)
      5. Update tag.name, db.session.commit()
    Returns 200 on success.
    """
    # Step 1: Validate JSON body (design.md section 4)
    data = request.get_json(silent=True)
    if data is None:
        return jsonify({"status": "error", "message": "请求体必须是 JSON"}), 400

    # Step 2: Extract and validate name (design.md 2.1)
    name = data.get('name')
    if not name or not isinstance(name, str) or not name.strip():
        return jsonify({"status": "error", "message": "name is required and must be a non-empty string"}), 400

    name = name.strip()

    # Step 3: Find tag by id (design.md 2.1)
    tag = Tag.query.get(id)
    if tag is None:
        return jsonify({"status": "error", "message": "资源未找到"}), 404

    # Step 4: Uniqueness check excluding self (design.md 3.1)
    # If new name is same as current, no-op (design.md 3.1 explicitly states this)
    duplicate = Tag.query.filter_by(name=name).filter(Tag.id != id).first()
    if duplicate:
        return jsonify({"status": "error", "message": "名称已存在"}), 409

    # Step 5: Update and commit (design.md 2.1)
    tag.name = name
    db.session.commit()

    return jsonify({"status": "ok", "data": _serialize_tag(tag)}), 200


@tag_bp.route('/tags/<int:id>', methods=['DELETE'])
def delete_tag(id):
    """DELETE /tags/<id> — Delete a tag and cascade-remove article-tag bindings.

    design.md 2.1:
      1. Find Tag.query.get(id); if not found -> 404
      2. db.session.delete(tag) + db.session.commit()
         SQLAlchemy auto-cascades to article_tags (design.md 2.1, 3.3)
    Returns 200 on success.
    """
    # Step 1: Find tag by id (design.md 2.1)
    tag = Tag.query.get(id)
    if tag is None:
        return jsonify({"status": "error", "message": "资源未找到"}), 404

    # Step 2: Delete — SQLAlchemy handles cascade to article_tags (design.md 3.3)
    db.session.delete(tag)
    db.session.commit()

    return jsonify({"status": "ok", "data": {"message": "Tag deleted"}}), 200
