"""
T2 RBAC System — Document Routes

Document CRUD with RBAC enforcement.
Register as a Flask Blueprint named 'document_bp'.

Permission requirements:
- GET /documents → doc.read (own tenant only)
- GET /documents/<id> → doc.read + same tenant
- POST /documents → doc.write
- PUT /documents/<id> → doc.write + (owner OR doc.write.any)
- DELETE /documents/<id> → doc.delete
"""

from flask import Blueprint, request, jsonify, g

from middleware import require_auth, get_user_permissions
from models import Document
from app import db

document_bp = Blueprint('document_bp', __name__)


def _doc_dict(doc):
    """Serialize a Document model instance to a plain dict."""
    return {
        'id': doc.id,
        'tenant_id': doc.tenant_id,
        'owner_id': doc.owner_id,
        'title': doc.title,
        'content': doc.content,
    }


@document_bp.route('/documents', methods=['GET'])
@require_auth
def list_documents():
    """List all documents for the current user's tenant. Requires doc.read."""
    perms = get_user_permissions(g.current_user)
    if 'doc.read' not in perms:
        return jsonify({'status': 'error', 'message': 'Permission denied'}), 403

    docs = Document.query.filter_by(tenant_id=g.current_user.tenant_id).all()
    return jsonify({'status': 'ok', 'data': [_doc_dict(d) for d in docs]}), 200


@document_bp.route('/documents/<int:doc_id>', methods=['GET'])
@require_auth
def get_document(doc_id):
    """Get a single document. Requires doc.read + same tenant."""
    perms = get_user_permissions(g.current_user)
    if 'doc.read' not in perms:
        return jsonify({'status': 'error', 'message': 'Permission denied'}), 403

    doc = Document.query.get(doc_id)
    if doc is None or doc.tenant_id != g.current_user.tenant_id:
        return jsonify({'status': 'error', 'message': 'Document not found'}), 404

    return jsonify({'status': 'ok', 'data': _doc_dict(doc)}), 200


@document_bp.route('/documents', methods=['POST'])
@require_auth
def create_document():
    """Create a document. Requires doc.write."""
    perms = get_user_permissions(g.current_user)
    if 'doc.write' not in perms:
        return jsonify({'status': 'error', 'message': 'Permission denied'}), 403

    body = request.get_json(silent=True) or {}
    title = body.get('title', '')
    content = body.get('content', '')

    doc = Document(
        tenant_id=g.current_user.tenant_id,
        owner_id=g.current_user.id,
        title=title,
        content=content,
    )
    db.session.add(doc)
    db.session.commit()

    return jsonify({'status': 'ok', 'data': _doc_dict(doc)}), 201


@document_bp.route('/documents/<int:doc_id>', methods=['PUT'])
@require_auth
def update_document(doc_id):
    """Update a document. Requires doc.write + (owner OR doc.write.any) + same tenant."""
    perms = get_user_permissions(g.current_user)
    if 'doc.write' not in perms:
        return jsonify({'status': 'error', 'message': 'Permission denied'}), 403

    doc = Document.query.get(doc_id)
    if doc is None or doc.tenant_id != g.current_user.tenant_id:
        return jsonify({'status': 'error', 'message': 'Document not found'}), 404

    # Owner check: must be the owner OR have doc.write.any permission
    if doc.owner_id != g.current_user.id and 'doc.write.any' not in perms:
        return jsonify({'status': 'error', 'message': 'Permission denied'}), 403

    body = request.get_json(silent=True) or {}
    if 'title' in body:
        doc.title = body['title']
    if 'content' in body:
        doc.content = body['content']

    db.session.commit()

    return jsonify({'status': 'ok', 'data': _doc_dict(doc)}), 200


@document_bp.route('/documents/<int:doc_id>', methods=['DELETE'])
@require_auth
def delete_document(doc_id):
    """Delete a document. Requires doc.delete + same tenant."""
    perms = get_user_permissions(g.current_user)
    if 'doc.delete' not in perms:
        return jsonify({'status': 'error', 'message': 'Permission denied'}), 403

    doc = Document.query.get(doc_id)
    if doc is None or doc.tenant_id != g.current_user.tenant_id:
        return jsonify({'status': 'error', 'message': 'Document not found'}), 404

    db.session.delete(doc)
    db.session.commit()

    return jsonify({'status': 'ok', 'data': _doc_dict(doc)}), 200
