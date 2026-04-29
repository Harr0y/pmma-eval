"""
T2 RBAC System — Document Routes

Document CRUD with RBAC enforcement.
"""

from flask import Blueprint, request, jsonify, g
from models import Document
from middleware import check_permission, require_auth
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
    data = request.get_json(silent=True)
    if not data or not data.get('title'):
        return jsonify({'status': 'error', 'message': 'Title is required'}), 400

    doc = Document(
        tenant_id=g.current_user.tenant_id,
        owner_id=g.current_user.id,
        title=data['title'],
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

    # Must be owner or have doc.write.any
    if doc.owner_id != g.current_user.id and 'doc.write.any' not in g.current_permissions:
        return jsonify({'status': 'error', 'message': 'Permission denied'}), 403

    data = request.get_json(silent=True)
    if data:
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
