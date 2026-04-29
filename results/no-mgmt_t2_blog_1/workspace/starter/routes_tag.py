"""
T2 Blog — Tag Routes

Implement tag CRUD routes.
Register as a Flask Blueprint named 'tag_bp'.
"""

from flask import Blueprint, request, jsonify
from app import db
from models import Tag, Article, article_tags

tag_bp = Blueprint('tag_bp', __name__)


@tag_bp.route('/tags', methods=['POST'])
def create_tag():
    data = request.get_json()
    if not data or not data.get('name'):
        return jsonify({'status': 'error', 'message': 'Tag name is required'}), 400

    name = data['name'].strip()
    if not name:
        return jsonify({'status': 'error', 'message': 'Tag name cannot be empty'}), 400

    existing = Tag.query.filter_by(name=name).first()
    if existing:
        return jsonify({'status': 'error', 'message': 'Tag already exists'}), 409

    tag = Tag(name=name)
    db.session.add(tag)
    db.session.commit()

    return jsonify({'status': 'ok', 'data': {'id': tag.id, 'name': tag.name}}), 201


@tag_bp.route('/tags', methods=['GET'])
def list_tags():
    tags = Tag.query.all()
    return jsonify({'status': 'ok', 'data': [{'id': t.id, 'name': t.name} for t in tags]}), 200


@tag_bp.route('/tags/<int:tag_id>', methods=['PUT'])
def update_tag(tag_id):
    tag = Tag.query.get(tag_id)
    if not tag:
        return jsonify({'status': 'error', 'message': 'Tag not found'}), 404

    data = request.get_json()
    if not data or not data.get('name'):
        return jsonify({'status': 'error', 'message': 'Tag name is required'}), 400

    name = data['name'].strip()
    if not name:
        return jsonify({'status': 'error', 'message': 'Tag name cannot be empty'}), 400

    existing = Tag.query.filter(Tag.name == name, Tag.id != tag_id).first()
    if existing:
        return jsonify({'status': 'error', 'message': 'Tag name already exists'}), 409

    tag.name = name
    db.session.commit()

    return jsonify({'status': 'ok', 'data': {'id': tag.id, 'name': tag.name}}), 200


@tag_bp.route('/tags/<int:tag_id>', methods=['DELETE'])
def delete_tag(tag_id):
    tag = Tag.query.get(tag_id)
    if not tag:
        return jsonify({'status': 'error', 'message': 'Tag not found'}), 404

    # Delete article-tag associations first
    db.session.execute(
        article_tags.delete().where(article_tags.c.tag_id == tag_id)
    )
    db.session.delete(tag)
    db.session.commit()

    return jsonify({'status': 'ok', 'data': {'message': 'Tag deleted'}}), 200
