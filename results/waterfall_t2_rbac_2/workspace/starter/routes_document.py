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
"""

from flask import Blueprint, request, jsonify, g
from models import Document
from middleware import check_permission
from app import db

document_bp = Blueprint('document_bp', __name__)


def _serialize_doc(doc):
    """Serialize a Document model instance to a dict."""
    return {
        'id': doc.id,
        'tenant_id': doc.tenant_id,
        'owner_id': doc.owner_id,
        'title': doc.title,
        'content': doc.content,
    }


# --- design.md 4.2: GET /documents ---
@document_bp.route('/documents', methods=['GET'])
@check_permission('doc.read')
def list_documents():
    """List all documents for the current user's tenant."""
    docs = Document.query.filter_by(tenant_id=g.current_user.tenant_id).all()
    return jsonify({'status': 'ok', 'data': [_serialize_doc(d) for d in docs]}), 200


# --- design.md 4.3: GET /documents/<id> ---
@document_bp.route('/documents/<int:id>', methods=['GET'])
@check_permission('doc.read')
def get_document(id):
    """Get a single document by ID. Returns 404 if not found or different tenant."""
    doc = Document.query.get(id)
    if doc is None:
        return jsonify({'status': 'error', 'message': 'Document not found'}), 404
    if doc.tenant_id != g.current_user.tenant_id:
        return jsonify({'status': 'error', 'message': 'Document not found'}), 404
    return jsonify({'status': 'ok', 'data': _serialize_doc(doc)}), 200


# --- design.md 4.4: POST /documents ---
@document_bp.route('/documents', methods=['POST'])
@check_permission('doc.write')
def create_document():
    """Create a new document. tenant_id and owner_id come from JWT."""
    data = request.get_json(silent=True)
    if data is None:
        return jsonify({'status': 'error', 'message': 'Request must be JSON'}), 400

    title = data.get('title')
    if not title:
        return jsonify({'status': 'error', 'message': 'title is required'}), 400

    content = data.get('content', '')
    doc = Document(
        tenant_id=g.current_user.tenant_id,
        owner_id=g.current_user.id,
        title=title,
        content=content,
    )
    db.session.add(doc)
    db.session.commit()

    return jsonify({'status': 'ok', 'data': _serialize_doc(doc)}), 201


# --- design.md 4.5: PUT /documents/<id> ---
@document_bp.route('/documents/<int:id>', methods=['PUT'])
@check_permission('doc.write')
def update_document(id):
    """Update a document. Requires owner or doc.write.any permission, same tenant."""
    doc = Document.query.get(id)
    if doc is None:
        return jsonify({'status': 'error', 'message': 'Document not found'}), 404
    if doc.tenant_id != g.current_user.tenant_id:
        return jsonify({'status': 'error', 'message': 'Document not found'}), 404

    # Owner check: must be owner OR have doc.write.any
    if doc.owner_id != g.current_user.id and 'doc.write.any' not in g.current_permissions:
        return jsonify({'status': 'error', 'message': 'Permission denied'}), 403

    data = request.get_json(silent=True)
    if data is None:
        return jsonify({'status': 'error', 'message': 'Request must be JSON'}), 400

    if 'title' in data:
        doc.title = data['title']
    if 'content' in data:
        doc.content = data['content']

    db.session.commit()
    return jsonify({'status': 'ok', 'data': _serialize_doc(doc)}), 200


# --- design.md 4.6: DELETE /documents/<id> ---
@document_bp.route('/documents/<int:id>', methods=['DELETE'])
@check_permission('doc.delete')
def delete_document(id):
    """Delete a document. No owner check — any user with doc.delete can delete
    documents within the same tenant."""
    doc = Document.query.get(id)
    if doc is None:
        return jsonify({'status': 'error', 'message': 'Document not found'}), 404
    if doc.tenant_id != g.current_user.tenant_id:
        return jsonify({'status': 'error', 'message': 'Document not found'}), 404

    serialized = _serialize_doc(doc)
    db.session.delete(doc)
    db.session.commit()
    return jsonify({'status': 'ok', 'data': serialized}), 200
