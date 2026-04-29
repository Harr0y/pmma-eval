"""
T2 Blog -- Tag Routes (Sample 2: Helper-function + Tag.query style)

Design decisions for this variant:
- Validation logic is extracted into standalone helper functions that return
  either a validated value or None, leaving the caller responsible for
  building the error response.  This keeps response construction in the
  route handlers and avoids "double-return" issues.
- Uses the Tag.query ORM interface (query.filter_by, query.get) rather than
  session.get() or db.get_or_404().  A custom _find_tag_or_fail() helper
  wraps the lookup + 404 check pattern.
- Each route handler reads like high-level orchestration: call helper, check
  result, commit, return.  The helpers encapsulate all the validation logic.
- On DELETE, explicitly clears the association table rows via the relationship
  before removing the Tag, making the cascade explicit rather than relying on
  DB-level CASCADE.
- The delete cascade uses tag.articles = [] which tells SQLAlchemy to remove
  the association rows from article_tags before the Tag itself is deleted.
"""

from flask import Blueprint, request, jsonify

tag_bp = Blueprint('tag_bp', __name__)


def _models():
    """Lazy-loader for models to avoid circular import at module level.

    models.py imports db from app.py, so we defer the import.
    """
    import models
    return models


# ---------------------------------------------------------------------------
# Response builders
# ---------------------------------------------------------------------------

def _ok(data, status_code=200):
    """Standard success envelope."""
    return jsonify({"status": "ok", "data": data}), status_code


def _error(message, status_code=400):
    """Standard error envelope."""
    return jsonify({"status": "error", "message": message}), status_code


# ---------------------------------------------------------------------------
# Validation helpers  (pure functions -- never call _error / jsonify)
# ---------------------------------------------------------------------------

def _validate_name(payload):
    """Extract and validate the 'name' field from a request payload.

    Returns (True, stripped_name) on success, or (False, error_tuple) on
    failure where error_tuple is (message, status_code).
    """
    name = payload.get("name")
    if name is None:
        return False, ("Tag name is required", 400)
    if not isinstance(name, str):
        return False, ("Tag name must be a string", 400)
    stripped = name.strip()
    if not stripped:
        return False, ("Tag name must not be empty", 400)
    return True, stripped


def _find_tag_or_fail(tag_id):
    """Look up a Tag by primary key using db.session.get().

    Returns the Tag object, or None if not found.  The caller decides how
    to respond (404).

    NOTE: We deliberately use db.session.get() here instead of
    db.get_or_404() or Tag.query.get().  This keeps the helper a pure
    lookup -- no auto-404 exception, no legacy query.get() warning.
    """
    m = _models()
    return m.db.session.get(m.Tag, tag_id)


def _is_name_available(name, exclude_id=None):
    """Return True if *name* is not taken by any Tag (optionally excluding
    one tag by id, useful for same-name no-op updates).
    """
    m = _models()
    query = m.Tag.query.filter_by(name=name)
    if exclude_id is not None:
        query = query.filter(m.Tag.id != exclude_id)
    return query.first() is None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@tag_bp.route("/tags", methods=["POST"])
def create_tag():
    """Create a new tag.

    Request body (JSON): {"name": "..."}
    Success: 201 {"status": "ok", "data": {"id": int, "name": str}}
    Errors:  400 name missing/empty  |  409 name already exists
    """
    m = _models()
    payload = request.get_json(silent=True) or {}

    valid, result = _validate_name(payload)
    if not valid:
        return _error(result[0], result[1])

    name = result
    if not _is_name_available(name):
        return _error(f"Tag '{name}' already exists", 409)

    tag = m.Tag(name=name)
    m.db.session.add(tag)
    m.db.session.commit()

    return _ok({"id": tag.id, "name": tag.name}, 201)


@tag_bp.route("/tags", methods=["GET"])
def list_tags():
    """Return every tag ordered by id.

    Success: 200 {"status": "ok", "data": [{"id": int, "name": str}, ...]}
    """
    m = _models()
    tags = m.Tag.query.order_by(m.Tag.id).all()
    data = [{"id": t.id, "name": t.name} for t in tags]
    return _ok(data)


@tag_bp.route("/tags/<int:tag_id>", methods=["PUT"])
def update_tag(tag_id):
    """Rename an existing tag.

    Request body (JSON): {"name": "..."}
    Success: 200 {"status": "ok", "data": {"id": int, "name": str}}
    Errors:  404 tag not found  |  400 name missing/empty  |  409 name taken
    """
    m = _models()
    tag = _find_tag_or_fail(tag_id)
    if tag is None:
        return _error(f"Tag {tag_id} not found", 404)

    payload = request.get_json(silent=True) or {}
    valid, result = _validate_name(payload)
    if not valid:
        return _error(result[0], result[1])

    name = result
    if not _is_name_available(name, exclude_id=tag_id):
        return _error(f"Tag '{name}' already exists", 409)

    tag.name = name
    m.db.session.commit()

    return _ok({"id": tag.id, "name": tag.name})


@tag_bp.route("/tags/<int:tag_id>", methods=["DELETE"])
def delete_tag(tag_id):
    """Delete a tag and explicitly remove its article-tag associations.

    Success: 200 {"status": "ok", "data": {"message": "Tag deleted"}}
    Errors:  404 tag not found
    """
    m = _models()
    tag = _find_tag_or_fail(tag_id)
    if tag is None:
        return _error(f"Tag {tag_id} not found", 404)

    # Explicitly sever association rows before deleting the Tag.
    # Setting tag.articles = [] tells SQLAlchemy to delete the rows in
    # the article_tags association table that reference this tag.
    tag.articles = []
    m.db.session.delete(tag)
    m.db.session.commit()

    return _ok({"message": "Tag deleted"})
