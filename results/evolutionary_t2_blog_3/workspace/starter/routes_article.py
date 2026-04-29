"""
T2 Blog — Article Routes (Gen 1 Sample 1, Variant)

Design strategy: Inherits the ATU-001 proven patterns (_resp factory,
namedtuple serialization) and extends them for article CRUD + tag binding.

Unique decisions in this variant:
- ArticleData namedtuple with deterministic field order (id, title, body)
- Tag binding via direct article_tags.insert() with IntegrityError guard
  (TOCTOU-safe, consistent with tag routes' duplicate detection)
- Tag unbinding via direct article_tags.delete() -- no ORM load needed
- Query-level tag filtering via JOIN on article_tags (not Python filtering)
- Eager tag loading only when requested (default list omits tags for speed)
"""

from collections import namedtuple
from flask import Blueprint, request, jsonify
from sqlalchemy.exc import IntegrityError

from app import db
from models import Article, Tag, article_tags

article_bp = Blueprint('article_bp', __name__)

# --- Serialization layer ---

ArticleData = namedtuple('ArticleData', ['id', 'title', 'body'])
TagData = namedtuple('TagData', ['id', 'name'])


def _serialize_article(article: Article) -> dict:
    """Convert an Article ORM object to a plain dict with stable key order."""
    return ArticleData(id=article.id, title=article.title, body=article.body)._asdict()


def _serialize_articles(articles) -> list:
    """Serialize a list/query of Article objects."""
    return [_serialize_article(a) for a in articles]


def _serialize_tag(tag: Tag) -> dict:
    """Convert a Tag ORM object to a plain dict with stable key order."""
    return TagData(id=tag.id, name=tag.name)._asdict()


def _serialize_tags(tags) -> list:
    """Serialize a list/query of Tag objects."""
    return [_serialize_tag(t) for t in tags]


# --- Response builder factory (inherited from ATU-001) ---

def _resp(status: str, data=None, message: str = None, code: int = 200):
    """
    Build a standardized JSON response envelope.
    Usage: return _resp('ok', data=article_dict, code=201)
           return _resp('error', message='Not found', code=404)
    """
    body = {'status': status}
    if status == 'ok':
        body['data'] = data
    else:
        body['message'] = message
    return jsonify(body), code


# --- Routes ---

@article_bp.route('/articles', methods=['GET'])
def list_articles():
    """
    List all articles. Supports optional tag filtering:
      ?tag=<name>   -- filter by tag name
      ?tag_id=<id>  -- filter by tag ID
    Returns 200 with list (empty if no matches).
    """
    tag_name = request.args.get('tag', '').strip() or None
    tag_id_str = request.args.get('tag_id', '').strip() or None

    query = Article.query.order_by(Article.id)

    if tag_name is not None:
        query = (
            query
            .join(article_tags, Article.id == article_tags.c.article_id)
            .join(Tag, article_tags.c.tag_id == Tag.id)
            .filter(Tag.name == tag_name)
        )
    elif tag_id_str is not None:
        try:
            tag_id = int(tag_id_str)
        except ValueError:
            return _resp('error', message='tag_id must be an integer', code=400)
        query = (
            query
            .join(article_tags, Article.id == article_tags.c.article_id)
            .filter(article_tags.c.tag_id == tag_id)
        )

    articles = query.all()
    return _resp('ok', data=_serialize_articles(articles))


@article_bp.route('/articles', methods=['POST'])
def create_article():
    """Create a new article. Requires title and body in JSON body."""
    payload = request.get_json(silent=True) or {}
    title = (payload.get('title') or '').strip()
    body = (payload.get('body') or '').strip()

    if not title or not body:
        missing = []
        if not title:
            missing.append('title')
        if not body:
            missing.append('body')
        return _resp('error', message=f'Missing required field(s): {", ".join(missing)}', code=400)

    article = Article(title=title, body=body)
    db.session.add(article)
    db.session.commit()

    return _resp('ok', data=_serialize_article(article), code=201)


@article_bp.route('/articles/<int:article_id>', methods=['GET'])
def get_article(article_id: int):
    """Get a single article by ID. Returns 404 if not found."""
    article = Article.query.get(article_id)
    if article is None:
        return _resp('error', message=f'Article {article_id} not found', code=404)

    return _resp('ok', data=_serialize_article(article))


@article_bp.route('/articles/<int:article_id>/tags', methods=['POST'])
def bind_tags(article_id: int):
    """
    Bind tags to an article.

    Uses direct INSERT on the association table with IntegrityError guard,
    which is TOCTOU-safe and avoids checking existence first.

    Request: {"tag_ids": [1, 2, 3]}
    Returns: 200 on success, 404 if article not found, 400 if any tag_id is invalid.
    """
    article = Article.query.get(article_id)
    if article is None:
        return _resp('error', message=f'Article {article_id} not found', code=404)

    payload = request.get_json(silent=True) or {}
    tag_ids = payload.get('tag_ids')

    if not isinstance(tag_ids, list) or len(tag_ids) == 0:
        return _resp('error', message='tag_ids must be a non-empty list of integers', code=400)

    # Validate all tag_ids exist before any inserts
    existing_tag_ids = set(
        t.id for t in Tag.query.filter(Tag.id.in_(tag_ids)).all()
    )
    missing = set(tag_ids) - existing_tag_ids
    if missing:
        return _resp('error', message=f'Tag(s) not found: {", ".join(str(tid) for tid in sorted(missing))}', code=400)

    # Insert bindings directly into the association table
    bound_count = 0
    for tid in tag_ids:
        stmt = article_tags.insert().values(article_id=article_id, tag_id=tid)
        try:
            db.session.execute(stmt)
            bound_count += 1
        except IntegrityError:
            db.session.rollback()
            # Already bound -- skip silently (idempotent)

    db.session.commit()
    return _resp('ok', data={'message': 'Tags bound', 'bound_count': bound_count})


@article_bp.route('/articles/<int:article_id>/tags', methods=['GET'])
def get_article_tags(article_id: int):
    """Get all tags bound to an article. Returns 404 if article not found."""
    article = Article.query.get(article_id)
    if article is None:
        return _resp('error', message=f'Article {article_id} not found', code=404)

    tags = sorted(article.tags, key=lambda t: t.id)
    return _resp('ok', data=_serialize_tags(tags))


@article_bp.route('/articles/<int:article_id>/tags/<int:tag_id>', methods=['DELETE'])
def unbind_tag(article_id: int, tag_id: int):
    """
    Remove the association between an article and a tag.

    Uses direct DELETE on the association table -- no ORM load needed.
    Returns 404 if the article does not exist.
    """
    article = Article.query.get(article_id)
    if article is None:
        return _resp('error', message=f'Article {article_id} not found', code=404)

    stmt = article_tags.delete().where(
        article_tags.c.article_id == article_id,
        article_tags.c.tag_id == tag_id,
    )
    result = db.session.execute(stmt)
    db.session.commit()

    if result.rowcount == 0:
        return _resp('error', message=f'Tag {tag_id} is not bound to article {article_id}', code=404)

    return _resp('ok', data={'message': 'Tag unbound'})
