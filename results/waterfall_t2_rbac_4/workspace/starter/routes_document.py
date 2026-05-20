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

Design spec: design.md section 2.2

IMPORTANT: Uses middleware.check_permission decorator for JWT auth and
permission checking. Documents are tenant-scoped -- users can only
see/edit their own tenant's docs.
"""

from flask import Blueprint, request, jsonify, g

from models import Document
from middleware import check_permission
from app import db

document_bp = Blueprint('document_bp', __name__)


def _serialize_doc(doc):
    """Serialize a Document model instance to a dict.

    Design spec: design.md section 3.3

    Returns: {"id": int, "tenant_id": int, "owner_id": int, "title": str, "content": str}
    """
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
    """List all documents for the current user's tenant.

    Design spec: design.md section 2.2 — GET /documents
    Permission: doc.read
    Multi-tenant isolation: only returns documents belonging to user's tenant.
    Success: 200 {"status": "ok", "data": [{...}, ...]}
    Errors: 401 (missing/invalid token), 403 (no doc.read permission)
    """
    user = g.current_user
    docs = Document.query.filter_by(tenant_id=user.tenant_id).all()
    return jsonify({'status': 'ok', 'data': [_serialize_doc(d) for d in docs]}), 200


@document_bp.route('/documents/<int:doc_id>', methods=['GET'])
@check_permission('doc.read')
def get_document(doc_id):
    """Get a single document by ID.

    Design spec: design.md section 2.2 — GET /documents/<id>
    Permission: doc.read + same tenant check
    Multi-tenant isolation: returns 404 if document belongs to different tenant.
    Success: 200 {"status": "ok", "data": {...}}
    Errors: 401, 403, 404 (not found or different tenant)
    """
    user = g.current_user
    doc = Document.query.get(doc_id)
    if doc is None or doc.tenant_id != user.tenant_id:
        return jsonify({'status': 'error', 'message': 'Document not found'}), 404
    return jsonify({'status': 'ok', 'data': _serialize_doc(doc)}), 200


@document_bp.route('/documents', methods=['POST'])
@check_permission('doc.write')
def create_document():
    """Create a new document.

    Design spec: design.md section 2.2 — POST /documents
    Permission: doc.write
    Request body: {"title": str, "content": str (optional, defaults to "")}
    Validation: title must not be empty.
    tenant_id is set from the current user's tenant.
    owner_id is set to the current user's ID.
    Success: 201 {"status": "ok", "data": {...}}
    Errors: 401, 403, 400 (title empty or invalid request)
    """
    user = g.current_user
    data = request.get_json(silent=True)
    if data is None:
        return jsonify({'status': 'error', 'message': 'Invalid request'}), 400

    title = data.get('title')
    if not title or not str(title).strip():
        return jsonify({'status': 'error', 'message': 'Title is required'}), 400

    content = data.get('content', '')
    doc = Document(
        tenant_id=user.tenant_id,
        owner_id=user.id,
        title=title,
        content=content,
    )
    db.session.add(doc)
    db.session.commit()

    return jsonify({'status': 'ok', 'data': _serialize_doc(doc)}), 201


@document_bp.route('/documents/<int:doc_id>', methods=['PUT'])
@check_permission('doc.write')
def update_document(doc_id):
    """Update an existing document.

    Design spec: design.md section 2.2 — PUT /documents/<id>
    Permission: doc.write + (owner OR doc.write.any) + same tenant check
    Request body: {"title": str, "content": str} (only provided fields are updated)
    Multi-tenant isolation: returns 404 if document belongs to different tenant.
    Ownership check: user must be the document owner OR have doc.write.any permission.
    Success: 200 {"status": "ok", "data": {...}}
    Errors: 401, 403 (not owner and no doc.write.any), 404 (not found or different tenant)
    """
    user = g.current_user
    perms = g.current_permissions

    # Step 1: Query document, enforce tenant isolation
    doc = Document.query.get(doc_id)
    if doc is None or doc.tenant_id != user.tenant_id:
        return jsonify({'status': 'error', 'message': 'Document not found'}), 404

    # Step 2: Check ownership or doc.write.any permission
    if doc.owner_id != user.id and 'doc.write.any' not in perms:
        return jsonify({'status': 'error', 'message': 'Permission denied'}), 403

    # Step 3: Partial update — only update fields that are provided
    data = request.get_json(silent=True)
    if data is None:
        return jsonify({'status': 'error', 'message': 'Invalid request'}), 400

    if 'title' in data:
        title = data['title']
        if not title or not str(title).strip():
            return jsonify({'status': 'error', 'message': 'Title is required'}), 400
        doc.title = title

    if 'content' in data:
        doc.content = data['content']

    db.session.commit()
    return jsonify({'status': 'ok', 'data': _serialize_doc(doc)}), 200


@document_bp.route('/documents/<int:doc_id>', methods=['DELETE'])
@check_permission('doc.delete')
def delete_document(doc_id):
    """Delete a document.

    Design spec: design.md section 2.2 — DELETE /documents/<id>
    Permission: doc.delete + same tenant check
    Multi-tenant isolation: returns 404 if document belongs to different tenant.
    Success: 200 {"status": "ok", "data": null}
    Errors: 401, 403, 404 (not found or different tenant)
    """
    user = g.current_user
    doc = Document.query.get(doc_id)
    if doc is None or doc.tenant_id != user.tenant_id:
        return jsonify({'status': 'error', 'message': 'Document not found'}), 404

    db.session.delete(doc)
    db.session.commit()
    return jsonify({'status': 'ok', 'data': None}), 200
