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
from middleware import check_permission
from app import db

document_bp = Blueprint('document_bp', __name__)


def _serialize_doc(doc):
    """Serialize a Document model instance to a JSON-serializable dict."""
    return {
        "id": doc.id,
        "tenant_id": doc.tenant_id,
        "owner_id": doc.owner_id,
        "title": doc.title,
        "content": doc.content,
    }


@document_bp.route('/documents', methods=['GET'])
@check_permission('doc.read')
def list_documents():
    """List all documents belonging to the current user's tenant.

    Requires doc.read permission. Only returns documents scoped to the
    authenticated user's tenant_id.
    """
    user = g.current_user
    docs = Document.query.filter_by(tenant_id=user.tenant_id).all()
    return jsonify({"status": "ok", "data": [_serialize_doc(d) for d in docs]}), 200


@document_bp.route('/documents/<int:doc_id>', methods=['GET'])
@check_permission('doc.read')
def get_document(doc_id):
    """Retrieve a single document by ID.

    Requires doc.read permission. Returns 404 if the document does not exist
    or belongs to a different tenant (tenant isolation).
    """
    user = g.current_user
    doc = Document.query.get(doc_id)
    if doc is None or doc.tenant_id != user.tenant_id:
        return jsonify({"status": "error", "message": "Not found"}), 404
    return jsonify({"status": "ok", "data": _serialize_doc(doc)}), 200


@document_bp.route('/documents', methods=['POST'])
@check_permission('doc.write')
def create_document():
    """Create a new document.

    Requires doc.write permission. The tenant_id is taken from the JWT,
    and owner_id is set to the authenticated user's ID.
    Returns 201 on success.
    """
    user = g.current_user
    data = request.get_json(silent=True)
    if data is None:
        return jsonify({"status": "error", "message": "Request must be JSON"}), 400

    title = data.get('title')
    content = data.get('content', '')
    if not title:
        return jsonify({"status": "error", "message": "Title is required"}), 400

    doc = Document(tenant_id=user.tenant_id, owner_id=user.id,
                   title=title, content=content)
    db.session.add(doc)
    db.session.commit()
    return jsonify({"status": "ok", "data": _serialize_doc(doc)}), 201


@document_bp.route('/documents/<int:doc_id>', methods=['PUT'])
@check_permission('doc.write')
def update_document(doc_id):
    """Update an existing document.

    Requires doc.write permission. The user must be the document owner OR
    have the doc.write.any permission. Returns 404 if the document does
    not exist or belongs to a different tenant. Returns 403 if the user
    is not the owner and lacks doc.write.any.
    """
    user = g.current_user
    perms = g.current_permissions

    doc = Document.query.get(doc_id)
    if doc is None or doc.tenant_id != user.tenant_id:
        return jsonify({"status": "error", "message": "Not found"}), 404

    if doc.owner_id != user.id and 'doc.write.any' not in perms:
        return jsonify({"status": "error", "message": "Permission denied"}), 403

    data = request.get_json(silent=True)
    if data is None:
        return jsonify({"status": "error", "message": "Request must be JSON"}), 400

    if 'title' in data:
        doc.title = data['title']
    if 'content' in data:
        doc.content = data['content']

    db.session.commit()
    return jsonify({"status": "ok", "data": _serialize_doc(doc)}), 200


@document_bp.route('/documents/<int:doc_id>', methods=['DELETE'])
@check_permission('doc.delete')
def delete_document(doc_id):
    """Delete a document.

    Requires doc.delete permission. Returns 404 if the document does not
    exist or belongs to a different tenant.
    """
    user = g.current_user
    doc = Document.query.get(doc_id)
    if doc is None or doc.tenant_id != user.tenant_id:
        return jsonify({"status": "error", "message": "Not found"}), 404

    deleted_id = doc.id
    db.session.delete(doc)
    db.session.commit()
    return jsonify({"status": "ok", "data": {"id": deleted_id}}), 200
