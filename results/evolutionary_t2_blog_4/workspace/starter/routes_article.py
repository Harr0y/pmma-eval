"""
routes_article_sample1.py -- Article CRUD + Tag Binding + Tag Filtering (Gen 1 Sample 1)

Evolutionary variant: Result dataclass pattern with Flask-free business logic,
extended to cover tag binding, unbinding, and tag-based article filtering.

Design decisions that differentiate this variant:
- A `Result` dataclass encapsulates business logic outcomes (success/error)
  with typed payloads, keeping helpers completely decoupled from Flask.
- A single `_respond()` adapter at the route layer translates Result objects
  into Flask responses, centralizing HTTP mapping in one place.
- Input validation uses a `Validator` class that accumulates multiple field
  errors before returning, providing richer error messages (e.g., reporting
  both missing title AND missing body in a single response).
- Article lookup uses `db.session.get()` (SQLAlchemy 2.0 primary-key lookup)
  instead of `select().where()` for single-record fetches -- a more idiomatic
  approach for PK-based access.
- The list endpoint uses `db.session.execute(select(...)).scalars().all()`
  (execute-then-scalars chain) rather than the shorthand `db.session.scalars()`,
  demonstrating a slightly different query composition style.
- Tag filtering in the list endpoint is handled inside the business logic layer
  by building the query with optional `where` clauses based on presence of
  filter parameters, keeping the route handler completely free of query details.
- Tag binding validates that all provided tag_ids exist before performing any
  inserts, returning a descriptive 404 if any tag_id is invalid.  This is a
  "validate-then-act" approach (vs. silent skip) -- the caller must fix their
  input rather than guessing which tags were silently dropped.
- Unbinding uses explicit `sa_delete(article_tags).where(...)` to remove the
  association row, matching the cascade-control pattern established in
  routes_tag.py for tag deletion.
"""

from dataclasses import dataclass
from typing import Any, Optional

from flask import Blueprint, request, jsonify
from sqlalchemy import select, delete as sa_delete

from app import db
from models import Article, Tag, article_tags

article_bp = Blueprint('article_bp', __name__)


# ---------------------------------------------------------------------------
# Result type -- pure data, no Flask dependency
# ---------------------------------------------------------------------------

@dataclass
class Result:
    """Encapsulates the outcome of a business-logic operation.

    Business helpers return Result objects; only the route layer converts
    them to HTTP responses.  This keeps the core logic testable without Flask.
    """
    ok: bool
    status_code: int
    data: Any = None
    message: str = ""


# ---------------------------------------------------------------------------
# Response adapter -- single point of Flask coupling
# ---------------------------------------------------------------------------

def _respond(result: Result):
    """Convert a Result into a Flask JSON response."""
    if result.ok:
        body = {"status": "ok", "data": result.data}
    else:
        body = {"status": "error", "message": result.message}
    return jsonify(body), result.status_code


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------

def _serialize_article(article: Article) -> dict:
    """Convert an Article ORM object to a plain dict."""
    return {"id": article.id, "title": article.title, "body": article.body}


def _serialize_articles(articles) -> list:
    """Convert an iterable of Article objects to a list of dicts."""
    return [_serialize_article(a) for a in articles]


def _serialize_tag(tag: Tag) -> dict:
    """Convert a Tag ORM object to a plain dict."""
    return {"id": tag.id, "name": tag.name}


# ---------------------------------------------------------------------------
# Input validation -- accumulates all field errors
# ---------------------------------------------------------------------------

class Validator:
    """Accumulates validation errors for a request payload.

    Unlike simple early-return validation, this collects every missing/invalid
    field so the client gets a comprehensive error message in one round trip.
    """

    def __init__(self, payload: Optional[dict]):
        self._payload = payload or {}
        self._errors: list[str] = []

    def require_string(self, field: str) -> Optional[str]:
        """Check that *field* is present and is a non-empty string.

        Returns the stripped value on success, or None (and records an error).
        """
        value = self._payload.get(field)
        if value is None:
            self._errors.append(f"'{field}' is required")
            return None
        if not isinstance(value, str) or not value.strip():
            self._errors.append(f"'{field}' must be a non-empty string")
            return None
        return value.strip()

    def to_result(self) -> Optional[Result]:
        """Return an error Result if any errors were collected, else None."""
        if self._errors:
            return Result(
                ok=False,
                status_code=400,
                message="; ".join(self._errors),
            )
        return None


# ---------------------------------------------------------------------------
# Business logic helpers -- all return Result, no Flask imports needed
# ---------------------------------------------------------------------------

def _create_article(title: str, body: str) -> Result:
    """Persist a new article and return it."""
    article = Article(title=title, body=body)
    db.session.add(article)
    db.session.commit()
    return Result(ok=True, status_code=201, data=_serialize_article(article))


def _list_articles(tag_name: Optional[str] = None, tag_id: Optional[int] = None) -> Result:
    """Fetch articles, optionally filtered by tag name or tag id.

    Strategy: Build a base select(Article) and conditionally join/filter
    against the association table and Tag model.  The join is applied only
    when a filter is present, avoiding unnecessary cross-products on the
    unfiltered list-all path.
    """
    stmt = select(Article).order_by(Article.id)

    if tag_id is not None:
        # Filter by tag id: join association table and match tag_id column.
        stmt = (
            stmt
            .join(article_tags, Article.id == article_tags.c.article_id)
            .where(article_tags.c.tag_id == tag_id)
        )
    elif tag_name is not None:
        # Filter by tag name: join through association table to Tag model.
        stmt = (
            stmt
            .join(article_tags, Article.id == article_tags.c.article_id)
            .join(Tag, Tag.id == article_tags.c.tag_id)
            .where(Tag.name == tag_name)
        )

    articles = db.session.execute(stmt).scalars().all()
    return Result(ok=True, status_code=200, data=_serialize_articles(articles))


def _get_article_by_id(article_id: int) -> Result:
    """Fetch a single article by primary key.

    Uses db.session.get() -- the SQLAlchemy 2.0 idiomatic way to load by PK,
    which is more direct than constructing a select().where(Article.id == ...).
    Returns 404 if the article does not exist.
    """
    article = db.session.get(Article, article_id)
    if article is None:
        return Result(ok=False, status_code=404, message="Article not found")
    return Result(ok=True, status_code=200, data=_serialize_article(article))


def _bind_tags_to_article(article_id: int, tag_ids: list[int]) -> Result:
    """Bind a set of tags to an article.

    Validates that the article exists and that every tag_id in the request
    refers to a real Tag.  If any tag_id is unknown, returns 404 with a
    message listing the invalid ids.  This "validate-then-act" approach
    prevents partial binding and forces the caller to correct their input.

    Existing bindings are silently skipped (idempotent).
    """
    article = db.session.get(Article, article_id)
    if article is None:
        return Result(ok=False, status_code=404, message="Article not found")

    if not tag_ids:
        # Empty tag_ids list is treated as a no-op success.
        return Result(ok=True, status_code=200, data={"message": "No tags to bind"})

    # Resolve all tag ids upfront to detect invalid ones before any writes.
    tags = db.session.execute(
        select(Tag).where(Tag.id.in_(tag_ids))
    ).scalars().all()

    found_ids = {t.id for t in tags}
    missing_ids = set(tag_ids) - found_ids
    if missing_ids:
        return Result(
            ok=False,
            status_code=404,
            message=f"Tag(s) not found: {', '.join(str(i) for i in sorted(missing_ids))}",
        )

    # Insert new association rows (skip duplicates).
    for tag in tags:
        if tag not in article.tags:
            article.tags.append(tag)

    db.session.commit()
    return Result(
        ok=True,
        status_code=200,
        data={"message": f"Bound {len(tags)} tag(s) to article {article_id}"},
    )


def _get_article_tags(article_id: int) -> Result:
    """Return all tags bound to the given article."""
    article = db.session.get(Article, article_id)
    if article is None:
        return Result(ok=False, status_code=404, message="Article not found")

    tags = db.session.execute(
        select(Tag)
        .join(article_tags, Tag.id == article_tags.c.tag_id)
        .where(article_tags.c.article_id == article_id)
        .order_by(Tag.id)
    ).scalars().all()

    return Result(ok=True, status_code=200, data=[_serialize_tag(t) for t in tags])


def _unbind_tag_from_article(article_id: int, tag_id: int) -> Result:
    """Remove the association between an article and a tag.

    Uses explicit sa_delete on the association table for cascade control,
    matching the pattern used in routes_tag.py for tag deletion.
    Returns 200 even if the binding did not exist (idempotent).
    """
    article = db.session.get(Article, article_id)
    if article is None:
        return Result(ok=False, status_code=404, message="Article not found")

    db.session.execute(
        sa_delete(article_tags).where(
            article_tags.c.article_id == article_id,
            article_tags.c.tag_id == tag_id,
        )
    )
    db.session.commit()
    return Result(ok=True, status_code=200, data={"message": "Tag unbound from article"})


# ---------------------------------------------------------------------------
# Route handlers -- thin adapters from HTTP to business logic
# ---------------------------------------------------------------------------

@article_bp.route("/articles", methods=["POST"])
def create_article():
    """POST /articles -- Create a new article."""
    payload = request.get_json(silent=True)
    v = Validator(payload)
    title = v.require_string("title")
    body = v.require_string("body")

    err = v.to_result()
    if err:
        return _respond(err)

    return _respond(_create_article(title, body))


@article_bp.route("/articles", methods=["GET"])
def list_articles():
    """GET /articles -- List all articles, optionally filtered by tag.

    Query parameters:
        tag     -- Filter by tag name (exact match).
        tag_id  -- Filter by tag id.
    """
    tag_name = request.args.get("tag")
    tag_id_str = request.args.get("tag_id")
    tag_id = int(tag_id_str) if tag_id_str else None
    return _respond(_list_articles(tag_name=tag_name, tag_id=tag_id))


@article_bp.route("/articles/<int:article_id>", methods=["GET"])
def get_article(article_id):
    """GET /articles/<id> -- Retrieve a single article."""
    return _respond(_get_article_by_id(article_id))


@article_bp.route("/articles/<int:article_id>/tags", methods=["POST"])
def bind_tags(article_id):
    """POST /articles/<id>/tags -- Bind tags to an article.

    Body: {"tag_ids": [1, 2, ...]}
    """
    payload = request.get_json(silent=True)
    if not payload or "tag_ids" not in payload:
        return _respond(Result(
            ok=False, status_code=400,
            message="'tag_ids' is required and must be a list of integers",
        ))

    tag_ids = payload["tag_ids"]
    if not isinstance(tag_ids, list) or not all(isinstance(tid, int) for tid in tag_ids):
        return _respond(Result(
            ok=False, status_code=400,
            message="'tag_ids' must be a list of integers",
        ))

    return _respond(_bind_tags_to_article(article_id, tag_ids))


@article_bp.route("/articles/<int:article_id>/tags", methods=["GET"])
def get_article_tags(article_id):
    """GET /articles/<id>/tags -- Get all tags bound to an article."""
    return _respond(_get_article_tags(article_id))


@article_bp.route("/articles/<int:article_id>/tags/<int:tag_id>", methods=["DELETE"])
def unbind_tag(article_id, tag_id):
    """DELETE /articles/<id>/tags/<tag_id> -- Unbind a tag from an article."""
    return _respond(_unbind_tag_from_article(article_id, tag_id))
