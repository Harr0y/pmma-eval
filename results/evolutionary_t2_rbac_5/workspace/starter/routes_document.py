"""
T2 RBAC System -- Document Routes (Sample 1, Gen 1 ATU-003)

Variant strategy: explicit error factory functions, set-based permission
intersection checks, split owner-vs-write_any logic into a dedicated
guard helper, and use a unified request-body parser that centralises
validation. Single-document lookups use db.session.get() while list
queries use filter_by() -- a deliberate mixed-query strategy.
"""

from flask import Blueprint, request, jsonify, g
from models import Document
from middleware import check_permission
from app import db

document_bp = Blueprint('document_bp', __name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _serialise(doc):
    """Convert a Document ORM row to a plain dict."""
    return {
        'id': doc.id,
        'tenant_id': doc.tenant_id,
        'owner_id': doc.owner_id,
        'title': doc.title,
        'content': doc.content,
    }


def _err(message, status):
    """Standardised error response factory."""
    return jsonify({'status': 'error', 'message': message}), status


def _parse_body():
    """Parse and validate JSON body. Returns (dict, error_response) tuple."""
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return None, _err('Request body must be JSON', 400)
    return body, None


def _fetch_doc_or_404(doc_id, tenant_id):
    """Look up a document by PK and verify tenant isolation.

    Returns (document, error_response).  If the document exists but belongs
    to a different tenant we still return 404 (no information leakage).
    """
    doc = db.session.get(Document, doc_id)
    if doc is None or doc.tenant_id != tenant_id:
        return None, _err('Document not found', 404)
    return doc, None


def _is_owner_or_has_write_any(doc):
    """Return True if the current user owns *doc* or has doc.write.any.

    Uses set intersection against g.current_permissions (a set populated by
    the check_permission decorator).
    """
    perms = g.current_permissions
    if doc.owner_id == g.current_user.id:
        return True
    # set intersection -- deliberately different from a simple `in` check
    return bool({'doc.write.any'} & perms)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@document_bp.route('/documents', methods=['GET'])
@check_permission('doc.read')
def list_documents():
    user = g.current_user
    docs = Document.query.filter_by(tenant_id=user.tenant_id).all()
    return jsonify({'status': 'ok', 'data': [_serialise(d) for d in docs]}), 200


@document_bp.route('/documents/<int:doc_id>', methods=['GET'])
@check_permission('doc.read')
def get_document(doc_id):
    user = g.current_user
    doc, err = _fetch_doc_or_404(doc_id, user.tenant_id)
    if err:
        return err
    return jsonify({'status': 'ok', 'data': _serialise(doc)}), 200


@document_bp.route('/documents', methods=['POST'])
@check_permission('doc.write')
def create_document():
    body, err = _parse_body()
    if err:
        return err

    title = body.get('title', '')
    content = body.get('content', '')
    user = g.current_user

    doc = Document(
        tenant_id=user.tenant_id,
        owner_id=user.id,
        title=title,
        content=content,
    )
    db.session.add(doc)
    db.session.commit()

    return jsonify({'status': 'ok', 'data': _serialise(doc)}), 201


@document_bp.route('/documents/<int:doc_id>', methods=['PUT'])
@check_permission('doc.write')
def update_document(doc_id):
    user = g.current_user
    doc, err = _fetch_doc_or_404(doc_id, user.tenant_id)
    if err:
        return err

    if not _is_owner_or_has_write_any(doc):
        return _err('You do not have permission to edit this document', 403)

    body, err = _parse_body()
    if err:
        return err

    if 'title' in body:
        doc.title = body['title']
    if 'content' in body:
        doc.content = body['content']

    db.session.commit()
    return jsonify({'status': 'ok', 'data': _serialise(doc)}), 200


@document_bp.route('/documents/<int:doc_id>', methods=['DELETE'])
@check_permission('doc.delete')
def delete_document(doc_id):
    user = g.current_user
    doc, err = _fetch_doc_or_404(doc_id, user.tenant_id)
    if err:
        return err

    db.session.delete(doc)
    db.session.commit()
    return jsonify({'status': 'ok', 'data': None}), 200
