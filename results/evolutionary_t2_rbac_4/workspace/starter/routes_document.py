"""
T2 RBAC System -- Document Routes (Sample 1: Decorator + Serializer Variant)

Document CRUD with RBAC enforcement using middleware.check_permission decorator.

Design decisions (evolutionary variant):
- Uses middleware.check_permission decorator for auth + permission gating.
  The decorator sets g.current_user and g.current_permissions so route
  handlers can access them without re-querying.
- Document serialization extracted into a standalone helper (_serialize_document)
  for consistency across list/get/create/update responses.
- PUT supports partial update: only fields present in the request body are
  modified. If 'title' or 'content' is absent, the existing value is kept.
- ORM query style: Document.query.filter_by(...) for tenant-scoped lookups.
- Early-return validation pattern (inherited from ATU): each check returns
  immediately on failure, keeping the happy path at minimal indentation.
- Defensive request body parsing: body is checked for None and isinstance(dict)
  before any field access.

Register as a Flask Blueprint named 'document_bp'.

Permission requirements:
- GET /documents       -> doc.read (own tenant only)
- GET /documents/<id>  -> doc.read + same tenant
- POST /documents      -> doc.write
- PUT /documents/<id>  -> doc.write + (owner OR doc.write.any) + same tenant
- DELETE /documents/<id> -> doc.delete + same tenant
"""

from flask import Blueprint, request, jsonify, g

from models import Document
from middleware import check_permission
from app import db

document_bp = Blueprint('document_bp', __name__)


def _serialize_document(doc):
    """Convert a Document ORM object to a plain dict for JSON responses.

    Returns:
        dict with keys: id, tenant_id, owner_id, title, content
    """
    return {
        'id': doc.id,
        'tenant_id': doc.tenant_id,
        'owner_id': doc.owner_id,
        'title': doc.title,
        'content': doc.content,
    }


# ------------------------------------------------------------------
# 1. GET /documents -- List documents (tenant-scoped)
# ------------------------------------------------------------------

@document_bp.route('/documents', methods=['GET'])
@check_permission('doc.read')
def list_documents():
    """Return all documents belonging to the current user's tenant.

    Requires: doc.read permission (enforced by decorator).

    Success (200):
        {"status": "ok", "data": [{"id": int, "tenant_id": int, "owner_id": int,
          "title": str, "content": str}, ...]}

    Errors:
        401 -- missing / invalid token (decorator)
        403 -- no doc.read permission (decorator)
    """
    tenant_id = g.current_user.tenant_id
    docs = Document.query.filter_by(tenant_id=tenant_id).all()
    data = [_serialize_document(d) for d in docs]
    return jsonify({'status': 'ok', 'data': data}), 200


# ------------------------------------------------------------------
# 2. GET /documents/<id> -- Get single document
# ------------------------------------------------------------------

@document_bp.route('/documents/<int:doc_id>', methods=['GET'])
@check_permission('doc.read')
def get_document(doc_id):
    """Retrieve a single document by ID, scoped to the current tenant.

    Requires: doc.read permission (enforced by decorator).

    Success (200):
        {"status": "ok", "data": {"id": int, "tenant_id": int, "owner_id": int,
          "title": str, "content": str}}

    Errors:
        401 -- missing / invalid token (decorator)
        403 -- no doc.read permission (decorator)
        404 -- document not found or belongs to a different tenant
    """
    doc = Document.query.filter_by(id=doc_id, tenant_id=g.current_user.tenant_id).first()
    if doc is None:
        return jsonify({'status': 'error', 'message': 'Document not found'}), 404
    return jsonify({'status': 'ok', 'data': _serialize_document(doc)}), 200


# ------------------------------------------------------------------
# 3. POST /documents -- Create document
# ------------------------------------------------------------------

@document_bp.route('/documents', methods=['POST'])
@check_permission('doc.write')
def create_document():
    """Create a new document owned by the current user.

    Requires: doc.write permission (enforced by decorator).

    Request JSON:
        {"title": str, "content": str}

    Success (201):
        {"status": "ok", "data": {"id": int, "tenant_id": int, "owner_id": int,
          "title": str, "content": str}}

    Errors:
        401 -- missing / invalid token (decorator)
        403 -- no doc.write permission (decorator)
        400 -- missing title or content
    """
    body = request.get_json(silent=True)
    if body is None or not isinstance(body, dict):
        return jsonify({'status': 'error', 'message': 'Invalid request body'}), 400

    title = body.get('title')
    if not title or not isinstance(title, str):
        return jsonify({'status': 'error', 'message': 'Missing or invalid title'}), 400

    content = body.get('content')
    if content is None or not isinstance(content, str):
        return jsonify({'status': 'error', 'message': 'Missing or invalid content'}), 400

    doc = Document(
        tenant_id=g.current_user.tenant_id,
        owner_id=g.current_user.id,
        title=title,
        content=content,
    )
    db.session.add(doc)
    db.session.commit()

    return jsonify({'status': 'ok', 'data': _serialize_document(doc)}), 201


# ------------------------------------------------------------------
# 4. PUT /documents/<id> -- Update document (partial)
# ------------------------------------------------------------------

@document_bp.route('/documents/<int:doc_id>', methods=['PUT'])
@check_permission('doc.write')
def update_document(doc_id):
    """Update an existing document. Supports partial update.

    Requires: doc.write permission (enforced by decorator) AND either
    the user is the document owner OR has the doc.write.any permission.

    Request JSON (at least one field required):
        {"title": str}              -- update title only
        {"content": str}            -- update content only
        {"title": str, "content": str} -- update both

    Success (200):
        {"status": "ok", "data": {"id": int, "tenant_id": int, "owner_id": int,
          "title": str, "content": str}}

    Errors:
        401 -- missing / invalid token (decorator)
        403 -- no doc.write permission (decorator) or not owner and no doc.write.any
        404 -- document not found or belongs to a different tenant
        400 -- invalid request body or no updatable fields provided
    """
    # --- Look up document (tenant-scoped) ---
    doc = Document.query.filter_by(id=doc_id, tenant_id=g.current_user.tenant_id).first()
    if doc is None:
        return jsonify({'status': 'error', 'message': 'Document not found'}), 404

    # --- Ownership check: owner can always edit; others need doc.write.any ---
    if doc.owner_id != g.current_user.id:
        if 'doc.write.any' not in g.current_permissions:
            return jsonify({'status': 'error', 'message': 'Permission denied'}), 403

    # --- Parse and apply partial update ---
    body = request.get_json(silent=True)
    if body is None or not isinstance(body, dict):
        body = {}

    updated = False

    if 'title' in body:
        new_title = body['title']
        if not isinstance(new_title, str):
            return jsonify({'status': 'error', 'message': 'Invalid title'}), 400
        doc.title = new_title
        updated = True

    if 'content' in body:
        new_content = body['content']
        if not isinstance(new_content, str):
            return jsonify({'status': 'error', 'message': 'Invalid content'}), 400
        doc.content = new_content
        updated = True

    if updated:
        db.session.commit()

    return jsonify({'status': 'ok', 'data': _serialize_document(doc)}), 200


# ------------------------------------------------------------------
# 5. DELETE /documents/<id> -- Delete document
# ------------------------------------------------------------------

@document_bp.route('/documents/<int:doc_id>', methods=['DELETE'])
@check_permission('doc.delete')
def delete_document(doc_id):
    """Delete a document by ID, scoped to the current tenant.

    Requires: doc.delete permission (enforced by decorator).

    Success (200):
        {"status": "ok", "data": {}}

    Errors:
        401 -- missing / invalid token (decorator)
        403 -- no doc.delete permission (decorator)
        404 -- document not found or belongs to a different tenant
    """
    doc = Document.query.filter_by(id=doc_id, tenant_id=g.current_user.tenant_id).first()
    if doc is None:
        return jsonify({'status': 'error', 'message': 'Document not found'}), 404

    db.session.delete(doc)
    db.session.commit()
    return jsonify({'status': 'ok', 'data': {}}), 200
