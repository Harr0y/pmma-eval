"""
T2 RBAC System — Document Routes

Document CRUD with RBAC enforcement.
Register as a Flask Blueprint named 'document_bp'.

Permission requirements:
- GET /documents -> doc.read (own tenant only)
- GET /documents/<id> -> doc.read + same tenant
- POST /documents -> doc.write
- PUT /documents/<id> -> doc.write + (owner OR doc.write.any)
- DELETE /documents/<id> -> doc.delete

IMPORTANT: Uses middleware.get_current_user() for JWT auth and
middleware.get_user_permissions() for permission checking.
Documents are tenant-scoped — users can only see/edit their own tenant's docs.
"""

from flask import Blueprint, request, jsonify, g
from models import Document
from app import db
from middleware import check_permission, get_current_user, get_user_permissions

document_bp = Blueprint('document_bp', __name__)


def _doc_dict(doc):
    return {
        'id': doc.id,
        'tenant_id': doc.tenant_id,
        'owner_id': doc.owner_id,
        'title': doc.title,
        'content': doc.content,
    }


@document_bp.route('/documents', methods=['GET'])
@check_permission('doc.read')
def list_documents():
    user = g.current_user
    docs = Document.query.filter_by(tenant_id=user.tenant_id).all()
    return jsonify({'status': 'ok', 'data': [_doc_dict(d) for d in docs]})


@document_bp.route('/documents/<int:doc_id>', methods=['GET'])
@check_permission('doc.read')
def get_document(doc_id):
    user = g.current_user
    doc = Document.query.get(doc_id)
    if doc is None or doc.tenant_id != user.tenant_id:
        return jsonify({'status': 'error', 'message': 'Document not found'}), 404
    return jsonify({'status': 'ok', 'data': _doc_dict(doc)})


@document_bp.route('/documents', methods=['POST'])
@check_permission('doc.write')
def create_document():
    user = g.current_user
    data = request.get_json(silent=True) or {}
    title = data.get('title', '')
    content = data.get('content', '')
    doc = Document(tenant_id=user.tenant_id, owner_id=user.id, title=title, content=content)
    db.session.add(doc)
    db.session.commit()
    return jsonify({'status': 'ok', 'data': _doc_dict(doc)}), 201


@document_bp.route('/documents/<int:doc_id>', methods=['PUT'])
@check_permission('doc.write')
def update_document(doc_id):
    user = g.current_user
    perms = g.current_permissions
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
    return jsonify({'status': 'ok', 'data': _doc_dict(doc)})


@document_bp.route('/documents/<int:doc_id>', methods=['DELETE'])
@check_permission('doc.delete')
def delete_document(doc_id):
    user = g.current_user
    doc = Document.query.get(doc_id)
    if doc is None or doc.tenant_id != user.tenant_id:
        return jsonify({'status': 'error', 'message': 'Document not found'}), 404
    db.session.delete(doc)
    db.session.commit()
    return jsonify({'status': 'ok', 'data': None})
