"""
T2 RBAC System — Document Routes (Sample 2)

Variant strategy:
- require_auth decorator for authentication, then manual permission checks
- Helper functions for response building and document serialization
- Early-return error pattern
- Owner check helper for PUT

Register as Flask Blueprint named 'document_bp'.
"""

from flask import Blueprint, request, jsonify, g
from middleware import require_auth
from models import Document
from app import db

document_bp = Blueprint('document_bp', __name__)


def _ok(data, status=200):
    return jsonify({'status': 'ok', 'data': data}), status


def _err(message, status):
    return jsonify({'status': 'error', 'message': message}), status


def _serialize(doc):
    """Convert a Document model instance to a dict."""
    return {
        'id': doc.id,
        'tenant_id': doc.tenant_id,
        'owner_id': doc.owner_id,
        'title': doc.title,
        'content': doc.content,
    }


def _check_perm(code):
    """Check if the current user (in g) has a specific permission.
    Returns True/False.
    """
    return code in g.get('current_permissions', set())


@document_bp.route('/documents', methods=['GET'])
@require_auth
def list_documents():
    if not _check_perm('doc.read'):
        return _err('Permission denied', 403)

    tenant_id = g.current_user.tenant_id
    docs = Document.query.filter_by(tenant_id=tenant_id).all()
    return _ok([_serialize(d) for d in docs])


@document_bp.route('/documents/<int:doc_id>', methods=['GET'])
@require_auth
def get_document(doc_id):
    if not _check_perm('doc.read'):
        return _err('Permission denied', 403)

    doc = Document.query.get(doc_id)
    if doc is None or doc.tenant_id != g.current_user.tenant_id:
        return _err('Document not found', 404)

    return _ok(_serialize(doc))


@document_bp.route('/documents', methods=['POST'])
@require_auth
def create_document():
    if not _check_perm('doc.write'):
        return _err('Permission denied', 403)

    body = request.get_json(silent=True)
    if not body:
        return _err('Missing request body', 400)

    title = body.get('title')
    if not title:
        return _err('Title is required', 400)

    doc = Document(
        tenant_id=g.current_user.tenant_id,
        owner_id=g.current_user.id,
        title=title,
        content=body.get('content', ''),
    )
    db.session.add(doc)
    db.session.commit()

    return _ok(_serialize(doc), 201)


@document_bp.route('/documents/<int:doc_id>', methods=['PUT'])
@require_auth
def update_document(doc_id):
    if not _check_perm('doc.write'):
        return _err('Permission denied', 403)

    doc = Document.query.get(doc_id)
    if doc is None:
        return _err('Document not found', 404)

    # Owner or doc.write.any check
    is_owner = doc.owner_id == g.current_user.id
    has_write_any = _check_perm('doc.write.any')
    if not is_owner and not has_write_any:
        return _err('Permission denied', 403)

    body = request.get_json(silent=True)
    if body:
        if 'title' in body:
            doc.title = body['title']
        if 'content' in body:
            doc.content = body['content']

    db.session.commit()
    return _ok(_serialize(doc))


@document_bp.route('/documents/<int:doc_id>', methods=['DELETE'])
@require_auth
def delete_document(doc_id):
    if not _check_perm('doc.delete'):
        return _err('Permission denied', 403)

    doc = Document.query.get(doc_id)
    if doc is None or doc.tenant_id != g.current_user.tenant_id:
        return _err('Document not found', 404)

    db.session.delete(doc)
    db.session.commit()
    return _ok({'deleted': doc_id})
