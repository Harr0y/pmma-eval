"""
T2 RBAC System -- Document Routes (Sample 1: Gen 1, Developer)

Full document CRUD with RBAC enforcement.

Design decisions (evolutionary variant):
- A single _doc_dict() helper serialises Document ORM objects into plain
  dicts, keeping the endpoint functions focused on business logic.
- PUT /documents/<id> uses a two-stage permission check: first verify
  doc.write at the decorator level, then inspect g.current_permissions for
  doc.write.any inside the handler. This avoids needing a second middleware
  call and keeps the "owner-or-write-any" policy in one readable block.
- All tenant scoping is done at the query level (filter_by(tenant_id=...)).
  Cross-tenant access always returns 404, never 403, to avoid leaking the
  existence of resources in other tenants.
- request.get_json(silent=True) is used consistently so malformed JSON
  never triggers Flask's built-in 400 handler.
- Validation is strict but simple: title and content are required for
  POST; for PUT, only the supplied fields are updated (partial update).

To activate: change app.py import from routes_document to routes_document_sample1.
"""

from flask import Blueprint, request, jsonify, g
from models import Document
from app import db
from middleware import check_permission

document_bp = Blueprint('document_bp', __name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _doc_dict(doc):
    """Serialise a Document model instance into a plain dict for JSON responses."""
    return {
        'id': doc.id,
        'tenant_id': doc.tenant_id,
        'owner_id': doc.owner_id,
        'title': doc.title,
        'content': doc.content,
    }


def _is_write_any():
    """Check whether the current user has the doc.write.any permission.

    Relies on g.current_permissions being populated by the check_permission
    decorator.  Falls back to False if the attribute is somehow missing.
    """
    perms = getattr(g, 'current_permissions', set())
    return 'doc.write.any' in perms


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@document_bp.route('/documents', methods=['GET'])
@check_permission('doc.read')
def list_documents():
    """Return all documents belonging to the current user's tenant."""
    user = g.current_user
    docs = Document.query.filter_by(tenant_id=user.tenant_id).all()
    return jsonify({'status': 'ok', 'data': [_doc_dict(d) for d in docs]})


@document_bp.route('/documents/<int:doc_id>', methods=['GET'])
@check_permission('doc.read')
def get_document(doc_id):
    """Return a single document by ID, scoped to the current tenant."""
    user = g.current_user
    doc = Document.query.filter_by(id=doc_id, tenant_id=user.tenant_id).first()
    if doc is None:
        return jsonify({'status': 'error', 'message': 'Not found'}), 404
    return jsonify({'status': 'ok', 'data': _doc_dict(doc)})


@document_bp.route('/documents', methods=['POST'])
@check_permission('doc.write')
def create_document():
    """Create a new document owned by the current user in their tenant."""
    user = g.current_user
    tenant_id = user.tenant_id

    data = request.get_json(silent=True)
    if not data or not isinstance(data, dict):
        return jsonify({'status': 'error', 'message': 'Invalid request'}), 400

    title = data.get('title')
    content = data.get('content')

    if not title or not isinstance(title, str) or not title.strip():
        return jsonify({'status': 'error', 'message': 'Title is required'}), 400

    if content is None:
        content = ''

    doc = Document(
        tenant_id=tenant_id,
        owner_id=user.id,
        title=title.strip(),
        content=content,
    )
    db.session.add(doc)
    db.session.commit()

    return jsonify({'status': 'ok', 'data': _doc_dict(doc)}), 201


@document_bp.route('/documents/<int:doc_id>', methods=['PUT'])
@check_permission('doc.write')
def update_document(doc_id):
    """Update a document. Requires doc.write plus either ownership or doc.write.any."""
    user = g.current_user
    tenant_id = user.tenant_id

    doc = Document.query.filter_by(id=doc_id, tenant_id=tenant_id).first()
    if doc is None:
        return jsonify({'status': 'error', 'message': 'Not found'}), 404

    # Ownership or doc.write.any required for modification
    if doc.owner_id != user.id and not _is_write_any():
        return jsonify({'status': 'error', 'message': 'Permission denied'}), 403

    data = request.get_json(silent=True)
    if not data or not isinstance(data, dict):
        return jsonify({'status': 'error', 'message': 'Invalid request'}), 400

    # Partial update: only overwrite fields that are explicitly provided
    if 'title' in data:
        title = data['title']
        if not title or not isinstance(title, str) or not title.strip():
            return jsonify({'status': 'error', 'message': 'Title is required'}), 400
        doc.title = title.strip()

    if 'content' in data:
        doc.content = data['content']

    db.session.commit()

    return jsonify({'status': 'ok', 'data': _doc_dict(doc)})


@document_bp.route('/documents/<int:doc_id>', methods=['DELETE'])
@check_permission('doc.delete')
def delete_document(doc_id):
    """Delete a document, scoped to the current tenant."""
    user = g.current_user
    tenant_id = user.tenant_id

    doc = Document.query.filter_by(id=doc_id, tenant_id=tenant_id).first()
    if doc is None:
        return jsonify({'status': 'error', 'message': 'Not found'}), 404

    db.session.delete(doc)
    db.session.commit()

    return jsonify({'status': 'ok', 'data': {'id': doc_id}})
