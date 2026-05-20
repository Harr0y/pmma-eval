"""
T2 Blog — Article Routes

Implement article CRUD and tag-binding routes.
Register as a Flask Blueprint named 'article_bp'.
"""

from flask import Blueprint, request, jsonify

from models import db, Article, Tag, article_tags

article_bp = Blueprint('article_bp', __name__)


@article_bp.route('/articles', methods=['GET'])
def list_articles():
    """List all articles, optionally filtered by tag name or tag id."""
    tag_name = request.args.get('tag')
    tag_id = request.args.get('tag_id')

    query = Article.query

    if tag_name is not None:
        tag = Tag.query.filter_by(name=tag_name).first()
        if tag is None:
            return jsonify(status='ok', data=[])
        query = query.filter(Article.tags.any(id=tag.id))

    if tag_id is not None:
        query = query.filter(Article.tags.any(id=int(tag_id)))

    articles = query.all()
    data = [{'id': a.id, 'title': a.title, 'body': a.body} for a in articles]
    return jsonify(status='ok', data=data)


@article_bp.route('/articles', methods=['POST'])
def create_article():
    """Create a new article. Requires title and body."""
    data = request.get_json()
    title = data.get('title') if data else None
    body = data.get('body') if data else None

    if not title or not body:
        return jsonify(status='error', message='title and body are required'), 400

    article = Article(title=title, body=body)
    db.session.add(article)
    db.session.commit()

    return jsonify(status='ok', data={'id': article.id, 'title': article.title, 'body': article.body}), 201


@article_bp.route('/articles/<int:article_id>', methods=['GET'])
def get_article(article_id):
    """Get a single article by id."""
    article = Article.query.get(article_id)
    if article is None:
        return jsonify(status='error', message='Article not found'), 404

    return jsonify(status='ok', data={'id': article.id, 'title': article.title, 'body': article.body})


@article_bp.route('/articles/<int:article_id>/tags', methods=['POST'])
def bind_tags(article_id):
    """Bind tags to an article. Body: {"tag_ids": [1, 2, ...]}"""
    article = Article.query.get(article_id)
    if article is None:
        return jsonify(status='error', message='Article not found'), 404

    data = request.get_json()
    tag_ids = data.get('tag_ids') if data else None

    if not tag_ids:
        return jsonify(status='error', message='tag_ids is required'), 400

    for tid in tag_ids:
        tag = Tag.query.get(tid)
        if tag is None:
            return jsonify(status='error', message=f'Tag {tid} not found'), 400
        if tag not in article.tags:
            article.tags.append(tag)

    db.session.commit()
    return jsonify(status='ok', data={'message': 'Tags bound'})


@article_bp.route('/articles/<int:article_id>/tags', methods=['GET'])
def get_article_tags(article_id):
    """Get all tags for an article."""
    article = Article.query.get(article_id)
    if article is None:
        return jsonify(status='error', message='Article not found'), 404

    data = [{'id': t.id, 'name': t.name} for t in article.tags]
    return jsonify(status='ok', data=data)


@article_bp.route('/articles/<int:article_id>/tags/<int:tag_id>', methods=['DELETE'])
def unbind_tag(article_id, tag_id):
    """Unbind a tag from an article."""
    article = Article.query.get(article_id)
    if article is None:
        return jsonify(status='error', message='Article not found'), 404

    tag = Tag.query.get(tag_id)
    if tag and tag in article.tags:
        article.tags.remove(tag)
        db.session.commit()

    return jsonify(status='ok', data={'message': 'Tag unbound'})
