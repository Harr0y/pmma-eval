"""
T2 Blog — Tag Routes (Gen 1 Sample 1)

Design strategy: Dataclass-driven serialization + response builder factory.
Instead of ad-hoc dict construction in every route, all Tag serialization goes
through a single TagData namedtuple. The response builder (`_resp`) centralizes
the {"status": ..., "data": ...} envelope so route bodies stay minimal.

Error handling uses a "try-then-check" pattern: attempt the DB operation first,
catch IntegrityError for duplicates, then check existence. This avoids TOCTOU
races and keeps the happy-path logic linear.

Unique decisions:
- TagData namedtuple for deterministic serialization order
- _resp() factory with status_code binding
- IntegrityError-first duplicate detection (catches DB-level unique constraint)
- Separate _serialize_tag / _serialize_tags to decouple shape from query logic
"""

from collections import namedtuple
from flask import Blueprint, request, jsonify
from sqlalchemy.exc import IntegrityError

from app import db
from models import Tag

tag_bp = Blueprint('tag_bp', __name__)

# --- Serialization layer (namedtuple gives deterministic field order) ---

TagData = namedtuple('TagData', ['id', 'name'])


def _serialize_tag(tag: Tag) -> dict:
    """Convert a Tag ORM object into a plain dict with a stable key order."""
    return TagData(id=tag.id, name=tag.name)._asdict()


def _serialize_tags(tags) -> list:
    """Serialize a list/query of Tag objects."""
    return [_serialize_tag(t) for t in tags]


# --- Response builder factory ---

def _resp(status: str, data=None, message: str = None, code: int = 200):
    """
    Build a standardized JSON response envelope.
    Usage: return _resp('ok', data=tag_dict, code=201)
           return _resp('error', message='Not found', code=404)
    """
    body = {'status': status}
    if status == 'ok':
        body['data'] = data
    else:
        body['message'] = message
    return jsonify(body), code


# --- Routes ---

@tag_bp.route('/tags', methods=['POST'])
def create_tag():
    """Create a new tag. Rejects missing name (400) or duplicates (409)."""
    payload = request.get_json(silent=True) or {}
    name = (payload.get('name') or '').strip()

    if not name:
        return _resp('error', message='Tag name is required', code=400)

    tag = Tag(name=name)
    db.session.add(tag)

    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return _resp('error', message=f'Tag "{name}" already exists', code=409)

    return _resp('ok', data=_serialize_tag(tag), code=201)


@tag_bp.route('/tags', methods=['GET'])
def list_tags():
    """Return all tags as a list."""
    tags = Tag.query.order_by(Tag.id).all()
    return _resp('ok', data=_serialize_tags(tags))


@tag_bp.route('/tags/<int:tag_id>', methods=['PUT'])
def update_tag(tag_id: int):
    """Rename an existing tag. Rejects missing name (400), not-found (404), or duplicate name (409)."""
    payload = request.get_json(silent=True) or {}
    name = (payload.get('name') or '').strip()

    if not name:
        return _resp('error', message='Tag name is required', code=400)

    tag = Tag.query.get(tag_id)
    if tag is None:
        return _resp('error', message=f'Tag {tag_id} not found', code=404)

    tag.name = name

    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return _resp('error', message=f'Tag "{name}" already exists', code=409)

    return _resp('ok', data=_serialize_tag(tag))


@tag_bp.route('/tags/<int:tag_id>', methods=['DELETE'])
def delete_tag(tag_id: int):
    """
    Delete a tag and cascade-removes all article-tag bindings.

    Because Tag uses a secondary relationship table (article_tags) via
    backref, SQLAlchemy will automatically delete the association rows when
    the Tag is deleted. We explicitly flush the delete to catch any edge
    cases before committing.
    """
    tag = Tag.query.get(tag_id)
    if tag is None:
        return _resp('error', message=f'Tag {tag_id} not found', code=404)

    db.session.delete(tag)
    db.session.commit()

    return _resp('ok', data={'message': 'Tag deleted'})
