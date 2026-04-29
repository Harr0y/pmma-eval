"""
T2 RBAC System -- Document Routes (Gen 1 Sample 1 Variant)

Document CRUD with RBAC enforcement.
Register as a Flask Blueprint named 'document_bp'.

Key design decisions (Sample 1 signature):
- GET routes use check_permission('doc.read') decorator for simple auth.
- POST uses check_permission('doc.write') decorator.
- PUT uses require_auth + manual permission checks for the complex
  (owner OR doc.write.any) logic that can't be expressed as a single
  permission code to the decorator.
- DELETE uses check_permission('doc.delete') decorator.
- _serialize_document() provides unified JSON serialization.
- _get_document_or_404() encapsulates document lookup + tenant isolation,
  returning (document, error_response) tuple consistent with middleware
  patterns.
"""

from flask import Blueprint, request, jsonify, g

from models import Document
from middleware import check_permission, require_auth
from app import db

document_bp = Blueprint('document_bp', __name__)


# ============================================================
# Helper Functions
# ============================================================


def _serialize_document(doc):
    """Serialize a Document model instance into a JSON-safe dict.

    Includes id, tenant_id, owner_id, title, and content fields
    to match the expected API response format.
    """
    return {
        'id': doc.id,
        'tenant_id': doc.tenant_id,
        'owner_id': doc.owner_id,
        'title': doc.title,
        'content': doc.content,
    }


def _get_document_or_404(doc_id):
    """Look up a document by ID with tenant isolation.

    Fetches the document and verifies it belongs to the current user's
    tenant. Returns a (document, error_response) tuple:
    - On success: (Document instance, None)
    - On failure: (None, (jsonify response, status_code))

    Cross-tenant access returns 404 to prevent information leakage about
    which document IDs exist in other tenants.
    """
    doc = db.session.get(Document, doc_id)
    if doc is None:
        return None, (
            jsonify({'status': 'error', 'message': 'Document not found'}),
            404,
        )

    tenant_id = g.current_user.tenant_id
    if doc.tenant_id != tenant_id:
        return None, (
            jsonify({'status': 'error', 'message': 'Document not found'}),
            404,
        )

    return doc, None


# ============================================================
# GET /documents -- List Documents
# ============================================================


@document_bp.route('/documents', methods=['GET'])
@check_permission('doc.read')
def list_documents():
    """GET /documents -- List all documents for the current user's tenant.

    Requires: doc.read permission

    Success (200):
        {"status": "ok", "data": [{"id": int, "tenant_id": int, "owner_id": int,
                  "title": str, "content": str}, ...]}

    Errors:
        403 -- Insufficient permissions (handled by decorator)
    """
    tenant_id = g.current_user.tenant_id
    documents = Document.query.filter_by(tenant_id=tenant_id).all()

    return jsonify({
        'status': 'ok',
        'data': [_serialize_document(doc) for doc in documents],
    }), 200


# ============================================================
# GET /documents/<id> -- Get Single Document
# ============================================================


@document_bp.route('/documents/<int:doc_id>', methods=['GET'])
@check_permission('doc.read')
def get_document(doc_id):
    """GET /documents/<id> -- Retrieve a single document by ID.

    Requires: doc.read permission + same tenant as the document.

    Success (200):
        {"status": "ok", "data": {"id": int, "tenant_id": int, "owner_id": int,
                  "title": str, "content": str}}

    Errors:
        403 -- Insufficient permissions (handled by decorator)
        404 -- Document not found or belongs to a different tenant
    """
    doc, error = _get_document_or_404(doc_id)
    if error:
        return error

    return jsonify({
        'status': 'ok',
        'data': _serialize_document(doc),
    }), 200


# ============================================================
# POST /documents -- Create Document
# ============================================================


@document_bp.route('/documents', methods=['POST'])
@check_permission('doc.write')
def create_document():
    """POST /documents -- Create a new document.

    Requires: doc.write permission

    Request body (JSON):
        {"title": str, "content": str}

    tenant_id is taken from the JWT token. owner_id is set to the
    current authenticated user.

    Success (201):
        {"status": "ok", "data": {"id": int, "tenant_id": int, "owner_id": int,
                  "title": str, "content": str}}

    Errors:
        400 -- Missing or invalid request body
        403 -- Insufficient permissions (handled by decorator)
    """
    body = request.get_json(silent=True)

    # Step 1: Validate request body structure
    if not isinstance(body, dict):
        return jsonify({'status': 'error', 'message': 'Request body must be a JSON object'}), 400

    title = body.get('title')
    if not title or not isinstance(title, str):
        return jsonify({'status': 'error', 'message': 'Missing or invalid title'}), 400

    content = body.get('content', '')
    if not isinstance(content, str):
        return jsonify({'status': 'error', 'message': 'Invalid content'}), 400

    # Step 2: Create document with tenant and owner from JWT
    doc = Document(
        tenant_id=g.current_user.tenant_id,
        owner_id=g.current_user.id,
        title=title,
        content=content,
    )
    db.session.add(doc)
    db.session.commit()

    return jsonify({
        'status': 'ok',
        'data': _serialize_document(doc),
    }), 201


# ============================================================
# PUT /documents/<id> -- Update Document
# ============================================================


@document_bp.route('/documents/<int:doc_id>', methods=['PUT'])
@require_auth
def update_document(doc_id):
    """PUT /documents/<id> -- Update an existing document.

    Requires: doc.write permission + (owner OR doc.write.any permission).
    Uses require_auth + manual permission checks because the access
    control logic (owner OR write.any) cannot be expressed as a single
    permission code for the check_permission decorator.

    Request body (JSON):
        {"title": str, "content": str}

    Success (200):
        {"status": 'ok', "data": {"id": int, "tenant_id": int, "owner_id": int,
                  "title": str, "content": str}}

    Errors:
        400 -- Missing or invalid request body
        403 -- No doc.write permission, or doc.write but not owner and no doc.write.any
        404 -- Document not found or belongs to a different tenant
    """
    perms = g.current_permissions

    # Step 1: Check base doc.write permission
    if 'doc.write' not in perms:
        return jsonify({'status': 'error', 'message': 'Permission denied'}), 403

    # Step 2: Look up document with tenant isolation
    doc, error = _get_document_or_404(doc_id)
    if error:
        return error

    # Step 3: Check ownership or doc.write.any permission
    if doc.owner_id != g.current_user.id and 'doc.write.any' not in perms:
        return jsonify({'status': 'error', 'message': 'Permission denied'}), 403

    # Step 4: Parse and validate request body
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({'status': 'error', 'message': 'Request body must be a JSON object'}), 400

    # Step 5: Apply updates (only update fields that are provided)
    if 'title' in body:
        title = body['title']
        if not isinstance(title, str) or not title:
            return jsonify({'status': 'error', 'message': 'Missing or invalid title'}), 400
        doc.title = title

    if 'content' in body:
        content = body['content']
        if not isinstance(content, str):
            return jsonify({'status': 'error', 'message': 'Invalid content'}), 400
        doc.content = content

    db.session.commit()

    return jsonify({
        'status': 'ok',
        'data': _serialize_document(doc),
    }), 200


# ============================================================
# DELETE /documents/<id> -- Delete Document
# ============================================================


@document_bp.route('/documents/<int:doc_id>', methods=['DELETE'])
@check_permission('doc.delete')
def delete_document(doc_id):
    """DELETE /documents/<id> -- Delete a document.

    Requires: doc.delete permission + same tenant as the document.

    Success (200):
        {"status": "ok", "data": {"message": "Document deleted"}}

    Errors:
        403 -- Insufficient permissions (handled by decorator)
        404 -- Document not found or belongs to a different tenant
    """
    doc, error = _get_document_or_404(doc_id)
    if error:
        return error

    db.session.delete(doc)
    db.session.commit()

    return jsonify({
        'status': 'ok',
        'data': {'message': 'Document deleted'},
    }), 200
