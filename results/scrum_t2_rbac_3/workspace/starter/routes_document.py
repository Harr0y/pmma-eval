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

from middleware import get_current_user, check_permission, get_user_permissions
from app import db
from models import Document

document_bp = Blueprint('document_bp', __name__)


@document_bp.route('/documents', methods=['GET'])
@check_permission('doc.read')
def list_documents():
    """List documents for the current user's tenant."""
    user = g.current_user
    docs = Document.query.filter_by(tenant_id=user.tenant_id).all()
    data = [
        {
            'id': d.id,
            'tenant_id': d.tenant_id,
            'owner_id': d.owner_id,
            'title': d.title,
            'content': d.content,
        }
        for d in docs
    ]
    return jsonify({'status': 'ok', 'data': data}), 200


@document_bp.route('/documents/<int:doc_id>', methods=['GET'])
@check_permission('doc.read')
def get_document(doc_id):
    """Get a single document by ID. Returns 404 if different tenant or not found."""
    user = g.current_user
    doc = Document.query.get(doc_id)
    if doc is None or doc.tenant_id != user.tenant_id:
        return jsonify({'status': 'error', 'message': 'Document not found'}), 404
    return jsonify({
        'status': 'ok',
        'data': {
            'id': doc.id,
            'tenant_id': doc.tenant_id,
            'owner_id': doc.owner_id,
            'title': doc.title,
            'content': doc.content,
        },
    }), 200


@document_bp.route('/documents', methods=['POST'])
@check_permission('doc.write')
def create_document():
    """Create a new document. tenant_id from JWT, owner_id = current user."""
    user = g.current_user
    data = request.get_json(silent=True) or {}
    title = data.get('title', '')
    content = data.get('content', '')

    doc = Document(
        tenant_id=user.tenant_id,
        owner_id=user.id,
        title=title,
        content=content,
    )
    db.session.add(doc)
    db.session.commit()

    return jsonify({
        'status': 'ok',
        'data': {
            'id': doc.id,
            'tenant_id': doc.tenant_id,
            'owner_id': doc.owner_id,
            'title': doc.title,
            'content': doc.content,
        },
    }), 201


@document_bp.route('/documents/<int:doc_id>', methods=['PUT'])
@check_permission('doc.write')
def update_document(doc_id):
    """Update a document. User must be owner OR have doc.write.any permission."""
    user = g.current_user
    perms = get_user_permissions(user)

    doc = Document.query.get(doc_id)
    if doc is None or doc.tenant_id != user.tenant_id:
        return jsonify({'status': 'error', 'message': 'Document not found'}), 404

    if doc.owner_id != user.id and 'doc.write.any' not in perms:
        return jsonify({'status': 'error', 'message': 'Permission denied'}), 403

    data = request.get_json(silent=True) or {}
    if 'title' in data:
        doc.title = data['title']
    if 'content' in data:
        doc.content = data['content']

    db.session.commit()

    return jsonify({
        'status': 'ok',
        'data': {
            'id': doc.id,
            'tenant_id': doc.tenant_id,
            'owner_id': doc.owner_id,
            'title': doc.title,
            'content': doc.content,
        },
    }), 200


@document_bp.route('/documents/<int:doc_id>', methods=['DELETE'])
@check_permission('doc.delete')
def delete_document(doc_id):
    """Delete a document. Returns 404 if different tenant or not found."""
    user = g.current_user

    doc = Document.query.get(doc_id)
    if doc is None or doc.tenant_id != user.tenant_id:
        return jsonify({'status': 'error', 'message': 'Document not found'}), 404

    db.session.delete(doc)
    db.session.commit()

    return jsonify({'status': 'ok', 'data': None}), 200
