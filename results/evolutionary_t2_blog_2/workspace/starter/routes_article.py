"""
T2 Blog -- Article Routes (Sample 1: join-based filtering with query builder helper)

Design decisions for this variant:
- Uses the ORM relationship directly for tag binding/unbinding operations.
  article.tags.append(tag) for binding, article.tags.remove(tag) for unbinding.
  This is the most "SQLAlchemy-native" approach -- no raw SQL, no manual
  association table inserts.
- Validation is entirely inline inside each route handler.  No helper
  functions, no (bool, result) tuples.  The logic is immediately visible
  without jumping between files.
- For binding (POST), validates ALL tag_ids first before mutating anything.
  This prevents partial binds when some IDs are invalid -- either all succeed
  or none do.  This is a "validate-then-mutate" strategy.
- For unbinding (DELETE), explicitly checks that the tag is currently bound
  to the article before removing.  If not bound, returns 404.  This makes
  unbinding idempotent-safe (you get a clear error if the binding doesn't
  exist) rather than silently succeeding.
- Uses db.session.get() for tag lookups instead of db.get_or_404() because
  we need to distinguish between "tag not found" (400) and "article not
  found" (404) with different error messages.
- Uses the _models() lazy-import pattern to avoid circular imports at module
  load time (models.py imports db from app.py).
- Response construction is inline: jsonify() calls are directly in the route
  handlers.  No _ok() / _error() envelope builders -- keeping the file
  self-contained without cross-file helper dependencies.

**Mutation for ATU-004 (filtering)**:
- Introduces a _build_filtered_article_query() helper that constructs a
  SQLAlchemy 2.0 select() statement with optional JOIN + WHERE clauses.
- The helper returns a ready-to-execute select statement; the route handler
  only calls execute() and serializes.
- Filtering by tag name uses JOIN(article_tags) -> JOIN(Tag) -> WHERE(Tag.name == :name).
- Filtering by tag_id uses JOIN(article_tags) -> WHERE(article_tags.c.tag_id == :id).
- The helper encapsulates the "build the query" concern so the route handler
  stays clean.  This is a "query object" micro-pattern.
- Empty string for ?tag= is treated as no-match (returns []).
- Non-numeric ?tag_id= falls through to the base query (no filter), returning
  all articles -- this is intentional: invalid numeric input degrades gracefully
  rather than erroring.
- Uses a custom _parse_query_params() parser instead of request.args because
  request.args (via parse_qs) treats '+' as space.  This would break tag names
  containing literal '+' characters like 'C++'.  Our parser uses urllib.parse.unquote
  which does NOT treat '+' as space, preserving the literal '+' in tag names.
"""

from flask import Blueprint, request, jsonify
from urllib.parse import unquote
from werkzeug.exceptions import NotFound

article_bp = Blueprint('article_bp', __name__)


def _models():
    """Lazy-loader for models to avoid circular import at module level.

    models.py imports db from app.py, so we defer the import.
    """
    import models
    return models


def _serialize_article(article):
    """Convert an Article ORM object to a plain dict for JSON responses."""
    return {"id": article.id, "title": article.title, "body": article.body}


def _parse_query_params():
    """Parse request query string without treating '+' as space.

    Flask's request.args uses urllib.parse.parse_qs internally, which decodes
    '+' as space (standard application/x-www-form-urlencoded behavior).  This
    breaks tag names containing literal '+' characters like 'C++', because the
    query string '?tag=C++' would be parsed as tag='C  ' (two spaces).

    This parser uses urllib.parse.unquote which does NOT treat '+' as space,
    so '?tag=C++' correctly yields tag='C++'.
    """
    decoded = unquote(request.query_string.decode('utf-8'))
    params = {}
    for part in decoded.split('&'):
        if '=' in part:
            key, value = part.split('=', 1)
            params[key] = value
    return params


def _build_filtered_article_query(m):
    """Build a SQLAlchemy 2.0 select() for articles, optionally filtered by tag.

    Examines query parameters for 'tag' and 'tag_id'.  Uses _parse_query_params()
    instead of request.args to preserve literal '+' characters in tag names.
    If 'tag' is present, joins through article_tags -> Tag and filters by name
    (exact match, case-sensitive).  Empty string for 'tag' yields a WHERE
    clause that matches nothing, so the result is an empty list.

    If 'tag_id' is present and can be parsed as an integer, joins through
    article_tags and filters by tag_id.  Non-numeric values for 'tag_id' are
    silently ignored (no filter applied, returns all articles).

    If neither parameter is present, returns a plain select ordered by id.

    Returns:
        A SQLAlchemy Select statement ready for session.execute().
    """
    params = _parse_query_params()
    tag_name = params.get('tag')
    tag_id_str = params.get('tag_id')

    # Base query: all articles ordered by id
    stmt = m.db.select(m.Article).order_by(m.Article.id)

    # Filter by tag name (exact, case-sensitive)
    if tag_name is not None:
        stmt = (
            stmt
            .join(m.article_tags, m.Article.id == m.article_tags.c.article_id)
            .join(m.Tag, m.article_tags.c.tag_id == m.Tag.id)
            .where(m.Tag.name == tag_name)
        )
        return stmt

    # Filter by tag_id (numeric only)
    if tag_id_str is not None:
        try:
            tag_id = int(tag_id_str)
        except (ValueError, TypeError):
            # Non-numeric tag_id: ignore, return all articles
            return stmt
        stmt = (
            stmt
            .join(m.article_tags, m.Article.id == m.article_tags.c.article_id)
            .where(m.article_tags.c.tag_id == tag_id)
        )
        return stmt

    # No filter parameters: return all articles
    return stmt


# ---------------------------------------------------------------------------
# Routes -- Article CRUD (no tag operations in this file)
# ---------------------------------------------------------------------------

@article_bp.route("/articles", methods=["POST"])
def create_article():
    """Create a new article.

    Request body (JSON): {"title": "...", "body": "..."}
    Success: 201 {"status": "ok", "data": {"id": int, "title": str, "body": str}}
    Errors:  400 if title or body is missing, null, empty, or whitespace-only
    """
    m = _models()
    payload = request.get_json(silent=True) or {}

    # Inline validation: title must be present, non-null, and non-blank
    raw_title = payload.get("title")
    if not isinstance(raw_title, str) or not raw_title.strip():
        return jsonify({"status": "error", "message": "title is required and must be a non-empty string"}), 400

    # Inline validation: body must be present, non-null, and non-blank
    raw_body = payload.get("body")
    if not isinstance(raw_body, str) or not raw_body.strip():
        return jsonify({"status": "error", "message": "body is required and must be a non-empty string"}), 400

    article = m.Article(title=raw_title.strip(), body=raw_body)
    m.db.session.add(article)
    m.db.session.commit()

    return jsonify({"status": "ok", "data": _serialize_article(article)}), 201


@article_bp.route("/articles", methods=["GET"])
def list_articles():
    """List articles, optionally filtered by tag.

    Query parameters:
      - tag=<name>   : filter by tag name (exact match, case-sensitive)
      - tag_id=<id>  : filter by tag id (numeric)
      - no params    : return all articles (original behavior)

    Success: 200 {"status": "ok", "data": [{"id": int, "title": str, "body": str}, ...]}
    Unknown query parameters are silently ignored.
    """
    m = _models()

    stmt = _build_filtered_article_query(m)
    result = m.db.session.execute(stmt)
    articles = result.scalars().all()

    data = [_serialize_article(a) for a in articles]
    return jsonify({"status": "ok", "data": data}), 200


@article_bp.route("/articles/<int:article_id>", methods=["GET"])
def get_article(article_id):
    """Retrieve a single article by id.

    Uses db.get_or_404() which raises a 404 automatically if not found.
    The article_id parameter is constrained to int by Flask's <int:> converter,
    so non-numeric URLs (e.g. /articles/abc) already return 404.

    Success: 200 {"status": "ok", "data": {"id": int, "title": str, "body": str}}
    Errors:  404 if article not found
    """
    m = _models()

    # db.get_or_404() raises NotFound if the row is absent.
    # We catch it here to return a JSON error body instead of the default HTML page.
    try:
        article = m.db.get_or_404(m.Article, article_id)
    except NotFound:
        return jsonify({"status": "error", "message": f"Article {article_id} not found"}), 404

    return jsonify({"status": "ok", "data": _serialize_article(article)}), 200


# ---------------------------------------------------------------------------
# Routes -- Article-Tag Binding
#
# Strategy: Use the ORM relationship (article.tags) directly.
#   - Binding:   article.tags.append(tag)   -- SQLAlchemy handles the
#                 association table insert automatically.
#   - Unbinding: article.tags.remove(tag)   -- SQLAlchemy handles the
#                 association table delete automatically.
#   - All validation is inline.  No helper functions.
#   - For binding: validate ALL tag_ids upfront, then mutate.  This prevents
#     partial binds when some IDs are invalid.
# ---------------------------------------------------------------------------

@article_bp.route("/articles/<int:article_id>/tags", methods=["POST"])
def bind_tags_to_article(article_id):
    """Bind one or more tags to an article.

    Request body (JSON): {"tag_ids": [1, 2, 3]}
    Success: 200 {"status": "ok", "data": {"message": "Tags bound"}}
    Errors:  404 if article not found
             400 if tag_ids is missing, empty, not a list, or contains
                 non-existent tag IDs

    Design: Validates all tag_ids before mutating anything.  If any tag_id
    in the list does not exist, the entire request fails with 400 -- no
    partial binding.  Duplicate tag_ids and already-bound tags are silently
    skipped (idempotent).
    """
    m = _models()

    # Look up the article first
    try:
        article = m.db.get_or_404(m.Article, article_id)
    except NotFound:
        return jsonify({"status": "error", "message": f"Article {article_id} not found"}), 404

    # Parse and validate request body
    payload = request.get_json(silent=True)
    if not payload or not isinstance(payload, dict):
        return jsonify({"status": "error", "message": "Request body must be JSON"}), 400

    tag_ids = payload.get("tag_ids")
    if tag_ids is None:
        return jsonify({"status": "error", "message": "tag_ids is required"}), 400
    if not isinstance(tag_ids, list) or len(tag_ids) == 0:
        return jsonify({"status": "error", "message": "tag_ids must be a non-empty list"}), 400

    # Validate all tag IDs exist before any mutation
    tags = []
    for tid in tag_ids:
        tag = m.db.session.get(m.Tag, tid)
        if tag is None:
            return jsonify({"status": "error", "message": f"Tag {tid} not found"}), 400
        tags.append(tag)

    # Append each tag to the article's tag collection.
    # SQLAlchemy handles duplicates gracefully -- appending an already-related
    # tag is a no-op, which satisfies the idempotency requirement.
    for tag in tags:
        if tag not in article.tags:
            article.tags.append(tag)

    m.db.session.commit()

    return jsonify({"status": "ok", "data": {"message": "Tags bound"}}), 200


@article_bp.route("/articles/<int:article_id>/tags", methods=["GET"])
def get_article_tags(article_id):
    """Get all tags bound to an article.

    Success: 200 {"status": "ok", "data": [{"id": int, "name": str}, ...]}
    Errors:  404 if article not found

    The returned tag list contains only id and name -- no article references.
    """
    m = _models()

    # Look up the article first
    try:
        article = m.db.get_or_404(m.Article, article_id)
    except NotFound:
        return jsonify({"status": "error", "message": f"Article {article_id} not found"}), 404

    # Build the response from the relationship collection
    data = [{"id": tag.id, "name": tag.name} for tag in article.tags]
    return jsonify({"status": "ok", "data": data}), 200


@article_bp.route("/articles/<int:article_id>/tags/<int:tag_id>", methods=["DELETE"])
def unbind_tag_from_article(article_id, tag_id):
    """Remove the binding between an article and a tag.

    Success: 200 {"status": "ok", "data": {"message": "Tag unbound"}}
    Errors:  404 if article not found, or if the tag is not currently bound
                 to this article

    Design: Checks that the binding actually exists before removing it.
    If the article doesn't have this tag, returns 404 rather than silently
    succeeding.  This gives callers a clear signal about the state.
    The tag itself is NOT deleted -- only the association row is removed.
    """
    m = _models()

    # Look up the article first
    try:
        article = m.db.get_or_404(m.Article, article_id)
    except NotFound:
        return jsonify({"status": "error", "message": f"Article {article_id} not found"}), 404

    # Verify the tag exists and is currently bound to this article
    tag = m.db.session.get(m.Tag, tag_id)
    if tag is None or tag not in article.tags:
        return jsonify({"status": "error", "message": f"Tag {tag_id} not found"}), 404

    # Remove the association via the ORM relationship
    article.tags.remove(tag)
    m.db.session.commit()

    return jsonify({"status": "ok", "data": {"message": "Tag unbound"}}), 200
