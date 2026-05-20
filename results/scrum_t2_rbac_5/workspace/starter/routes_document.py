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

Requirements:
- GET /documents -> List documents for current user's tenant
  Requires: doc.read permission
  Response: {"status": "ok", "data": [{"id": int, "tenant_id": int, "owner_id": int,
            "title": str, "content": str}, ...]}

- POST /documents -> Create document
  Requires: doc.write permission
  Request: {"title": str, "content": str}
  Response: {"status": "ok", "data": {"id": int, "tenant_id": int, "owner_id": int,
            "title": str, "content": str}}
  - tenant_id from JWT, owner_id = current user

- GET /documents/<id> -> Get single document
  Requires: doc.read + same tenant
  Response: same as above
  Errors: 404 if not found or different tenant

- PUT /documents/<id> -> Update document
  Requires: doc.write + (owner OR doc.write.any permission) + same tenant
  Request: {"title": str, "content": str}
  Errors: 404 if not found, 403 if not owner and no doc.write.any

- DELETE /documents/<id> -> Delete document
  Requires: doc.delete permission + same tenant
  Errors: 404 if not found, 403 if no permission

IMPORTANT: Uses middleware.get_current_user() for JWT auth and
middleware.get_user_permissions() for permission checking.
Documents are tenant-scoped — users can only see/edit their own tenant's docs.
"""

from flask import Blueprint, request, jsonify, g
from middleware import check_permission
from models import Document
from app import db

document_bp = Blueprint('document_bp', __name__)


def _doc_to_dict(doc):
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
    docs = Document.query.filter_by(tenant_id=g.current_user.tenant_id).all()
    return jsonify({'status': 'ok', 'data': [_doc_to_dict(d) for d in docs]}), 200


@document_bp.route('/documents', methods=['POST'])
@check_permission('doc.write')
def create_document():
    data = request.get_json()
    doc = Document(
        tenant_id=g.current_user.tenant_id,
        owner_id=g.current_user.id,
        title=data.get('title', ''),
        content=data.get('content', ''),
    )
    db.session.add(doc)
    db.session.commit()
    return jsonify({'status': 'ok', 'data': _doc_to_dict(doc)}), 201


@document_bp.route('/documents/<int:doc_id>', methods=['GET'])
@check_permission('doc.read')
def get_document(doc_id):
    doc = Document.query.get(doc_id)
    if doc is None or doc.tenant_id != g.current_user.tenant_id:
        return jsonify({'status': 'error', 'message': 'Document not found'}), 404
    return jsonify({'status': 'ok', 'data': _doc_to_dict(doc)}), 200


@document_bp.route('/documents/<int:doc_id>', methods=['PUT'])
@check_permission('doc.write')
def update_document(doc_id):
    doc = Document.query.get(doc_id)
    if doc is None or doc.tenant_id != g.current_user.tenant_id:
        return jsonify({'status': 'error', 'message': 'Document not found'}), 404
    if doc.owner_id != g.current_user.id and 'doc.write.any' not in g.current_permissions:
        return jsonify({'status': 'error', 'message': 'Permission denied'}), 403
    data = request.get_json()
    if 'title' in data:
        doc.title = data['title']
    if 'content' in data:
        doc.content = data['content']
    db.session.commit()
    return jsonify({'status': 'ok', 'data': _doc_to_dict(doc)}), 200


@document_bp.route('/documents/<int:doc_id>', methods=['DELETE'])
@check_permission('doc.delete')
def delete_document(doc_id):
    doc = Document.query.get(doc_id)
    if doc is None or doc.tenant_id != g.current_user.tenant_id:
        return jsonify({'status': 'error', 'message': 'Document not found'}), 404
    db.session.delete(doc)
    db.session.commit()
    return jsonify({'status': 'ok', 'data': None}), 200
