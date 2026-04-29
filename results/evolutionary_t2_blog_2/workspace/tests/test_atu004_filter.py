"""
ATU-004: Article Filtering by Tag -- complete unit tests.

Covers the GET /articles endpoint with query parameter filtering:
- GET /articles?tag=Python       -- filter by tag name
- GET /articles?tag_id=1         -- filter by tag id
- GET /articles                  -- no filter, return all articles (original behavior)

Test categories:
- Filter by tag name (normal flow + edge cases)
- Filter by tag id (normal flow + edge cases)
- No filter parameter (preserve original behavior)
- Response structure validation
- Cross-endpoint consistency (bind/unbind then filter)
- Boundary conditions (empty DB, non-existent tags, etc.)
"""

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'starter'))

from app import create_app, db
from models import Article, Tag


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def client():
    """Create a fresh test client with an in-memory database."""
    app = create_app()
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'

    with app.test_client() as c:
        with app.app_context():
            db.drop_all()
            db.create_all()
        yield c


@pytest.fixture
def seeded_data(client):
    """Seed the database with a realistic set of articles and tags.

    Returns a dict with:
      - articles: list of article dicts (id, title, body)
      - tags: list of tag dicts (id, name)
      - bindings: list of (article_id, tag_id) tuples
    """
    # Create tags
    python = client.post('/tags', json={'name': 'Python'}).json['data']
    flask = client.post('/tags', json={'name': 'Flask'}).json['data']
    rust = client.post('/tags', json={'name': 'Rust'}).json['data']

    # Create articles
    a1 = client.post('/articles', json={'title': 'Python Basics', 'body': 'Learn Python fundamentals'}).json['data']
    a2 = client.post('/articles', json={'title': 'Flask Tutorial', 'body': 'Build web apps with Flask'}).json['data']
    a3 = client.post('/articles', json={'title': 'Rust Systems Programming', 'body': 'Low-level Rust'}).json['data']
    a4 = client.post('/articles', json={'title': 'Untagged Post', 'body': 'No tags here'}).json['data']

    # Bind tags to articles
    # a1: Python
    client.post(f'/articles/{a1["id"]}/tags', json={'tag_ids': [python['id']]})
    # a2: Python, Flask
    client.post(f'/articles/{a2["id"]}/tags', json={'tag_ids': [python['id'], flask['id']]})
    # a3: Rust
    client.post(f'/articles/{a3["id"]}/tags', json={'tag_ids': [rust['id']]})
    # a4: no tags

    return {
        'articles': [a1, a2, a3, a4],
        'tags': [python, flask, rust],
        'bindings': [
            (a1['id'], python['id']),
            (a2['id'], python['id']),
            (a2['id'], flask['id']),
            (a3['id'], rust['id']),
        ],
    }


# ============================================================
# GET /articles?tag=<name> -- Filter by tag name
# ============================================================

class TestFilterByTagName:
    """GET /articles?tag=Python -- filter articles by tag name."""

    def test_filter_by_tag_name_single_result(self, client, seeded_data):
        """Filtering by 'Rust' returns exactly one article."""
        resp = client.get('/articles?tag=Rust')
        assert resp.status_code == 200
        assert resp.json['status'] == 'ok'
        assert len(resp.json['data']) == 1
        assert resp.json['data'][0]['title'] == 'Rust Systems Programming'

    def test_filter_by_tag_name_multiple_results(self, client, seeded_data):
        """Filtering by 'Python' returns both Python-tagged articles."""
        resp = client.get('/articles?tag=Python')
        assert resp.status_code == 200
        assert len(resp.json['data']) == 2
        titles = {a['title'] for a in resp.json['data']}
        assert titles == {'Python Basics', 'Flask Tutorial'}

    def test_filter_by_tag_name_no_match(self, client, seeded_data):
        """Filtering by a non-existent tag name returns an empty list."""
        resp = client.get('/articles?tag=NonExistentTag')
        assert resp.status_code == 200
        assert resp.json['status'] == 'ok'
        assert resp.json['data'] == []

    def test_filter_by_tag_name_empty_string(self, client, seeded_data):
        """Filtering by an empty tag name returns an empty list."""
        resp = client.get('/articles?tag=')
        assert resp.status_code == 200
        assert resp.json['data'] == []

    def test_filter_by_tag_name_excludes_untagged(self, client, seeded_data):
        """Filtering by tag name must not include articles without that tag."""
        resp = client.get('/articles?tag=Python')
        titles = [a['title'] for a in resp.json['data']]
        assert 'Untagged Post' not in titles

    def test_filter_by_tag_name_excludes_other_tags(self, client, seeded_data):
        """Filtering by 'Flask' must not include Rust-only articles."""
        resp = client.get('/articles?tag=Flask')
        titles = [a['title'] for a in resp.json['data']]
        assert 'Rust Systems Programming' not in titles
        assert 'Python Basics' not in titles

    def test_filter_by_tag_name_case_sensitivity(self, client, seeded_data):
        """Tag name filtering should be case-sensitive (exact match)."""
        resp = client.get('/articles?tag=python')  # lowercase
        # 'python' != 'Python', so should return empty
        assert resp.status_code == 200
        assert resp.json['data'] == []

    def test_filter_by_tag_name_response_structure(self, client, seeded_data):
        """Each article in the filtered result has id, title, body (int, str, str)."""
        resp = client.get('/articles?tag=Python')
        for article in resp.json['data']:
            assert isinstance(article['id'], int)
            assert isinstance(article['title'], str)
            assert isinstance(article['body'], str)
            assert set(article.keys()) == {'id', 'title', 'body'}


# ============================================================
# GET /articles?tag_id=<id> -- Filter by tag id
# ============================================================

class TestFilterByTagId:
    """GET /articles?tag_id=1 -- filter articles by tag id."""

    def test_filter_by_tag_id_single_result(self, client, seeded_data):
        """Filtering by the Rust tag id returns exactly one article."""
        rust_tag = [t for t in seeded_data['tags'] if t['name'] == 'Rust'][0]
        resp = client.get(f'/articles?tag_id={rust_tag["id"]}')
        assert resp.status_code == 200
        assert resp.json['status'] == 'ok'
        assert len(resp.json['data']) == 1
        assert resp.json['data'][0]['title'] == 'Rust Systems Programming'

    def test_filter_by_tag_id_multiple_results(self, client, seeded_data):
        """Filtering by the Python tag id returns both Python-tagged articles."""
        python_tag = [t for t in seeded_data['tags'] if t['name'] == 'Python'][0]
        resp = client.get(f'/articles?tag_id={python_tag["id"]}')
        assert resp.status_code == 200
        assert len(resp.json['data']) == 2
        titles = {a['title'] for a in resp.json['data']}
        assert titles == {'Python Basics', 'Flask Tutorial'}

    def test_filter_by_tag_id_no_match(self, client, seeded_data):
        """Filtering by a non-existent tag id returns an empty list."""
        resp = client.get('/articles?tag_id=99999')
        assert resp.status_code == 200
        assert resp.json['status'] == 'ok'
        assert resp.json['data'] == []

    def test_filter_by_tag_id_zero(self, client, seeded_data):
        """Filtering by tag_id=0 (no tag has id 0) returns empty list."""
        resp = client.get('/articles?tag_id=0')
        assert resp.status_code == 200
        assert resp.json['data'] == []

    def test_filter_by_tag_id_excludes_untagged(self, client, seeded_data):
        """Filtering by tag id must not include articles without that tag."""
        python_tag = [t for t in seeded_data['tags'] if t['name'] == 'Python'][0]
        resp = client.get(f'/articles?tag_id={python_tag["id"]}')
        titles = [a['title'] for a in resp.json['data']]
        assert 'Untagged Post' not in titles

    def test_filter_by_tag_id_response_structure(self, client, seeded_data):
        """Each article in the filtered result has id, title, body."""
        flask_tag = [t for t in seeded_data['tags'] if t['name'] == 'Flask'][0]
        resp = client.get(f'/articles?tag_id={flask_tag["id"]}')
        for article in resp.json['data']:
            assert isinstance(article['id'], int)
            assert isinstance(article['title'], str)
            assert isinstance(article['body'], str)
            assert set(article.keys()) == {'id', 'title', 'body'}


# ============================================================
# GET /articles (no filter) -- Original behavior preserved
# ============================================================

class TestNoFilter:
    """GET /articles without any query parameters returns all articles."""

    def test_no_filter_returns_all(self, client, seeded_data):
        """Without filter parameters, all articles are returned."""
        resp = client.get('/articles')
        assert resp.status_code == 200
        assert resp.json['status'] == 'ok'
        assert len(resp.json['data']) == 4

    def test_no_filter_includes_untagged(self, client, seeded_data):
        """Without filter, untagged articles are also included."""
        resp = client.get('/articles')
        titles = [a['title'] for a in resp.json['data']]
        assert 'Untagged Post' in titles

    def test_no_filter_empty_database(self, client):
        """With no articles in the database, return an empty list."""
        resp = client.get('/articles')
        assert resp.status_code == 200
        assert resp.json['status'] == 'ok'
        assert resp.json['data'] == []

    def test_no_filter_response_structure(self, client, seeded_data):
        """Each article in the unfiltered list has id, title, body."""
        resp = client.get('/articles')
        for article in resp.json['data']:
            assert isinstance(article['id'], int)
            assert isinstance(article['title'], str)
            assert isinstance(article['body'], str)
            assert set(article.keys()) == {'id', 'title', 'body'}

    def test_no_filter_other_query_params_ignored(self, client, seeded_data):
        """Unknown query parameters should be ignored; all articles returned."""
        resp = client.get('/articles?unknown_param=value')
        assert resp.status_code == 200
        assert len(resp.json['data']) == 4


# ============================================================
# Cross-endpoint consistency: bind/unbind then filter
# ============================================================

class TestFilterAfterMutation:
    """Verify that filtering reflects the latest bind/unbind state."""

    def test_filter_after_bind(self, client):
        """After binding a tag, filtering by that tag returns the article."""
        article = client.post('/articles', json={'title': 'New Post', 'body': 'Content'}).json['data']
        tag = client.post('/tags', json={'name': 'Django'}).json['data']

        # Before binding, no articles match
        resp = client.get(f'/articles?tag_id={tag["id"]}')
        assert len(resp.json['data']) == 0

        # Bind the tag
        client.post(f'/articles/{article["id"]}/tags', json={'tag_ids': [tag['id']]})

        # After binding, the article appears
        resp = client.get(f'/articles?tag_id={tag["id"]}')
        assert len(resp.json['data']) == 1
        assert resp.json['data'][0]['title'] == 'New Post'

    def test_filter_after_unbind(self, client):
        """After unbinding a tag, filtering no longer returns that article."""
        article = client.post('/articles', json={'title': 'Post', 'body': 'Content'}).json['data']
        tag = client.post('/tags', json={'name': 'Redis'}).json['data']

        client.post(f'/articles/{article["id"]}/tags', json={'tag_ids': [tag['id']]})

        # Before unbinding, the article is found
        resp = client.get(f'/articles?tag=Redis')
        assert len(resp.json['data']) == 1

        # Unbind
        client.delete(f'/articles/{article["id"]}/tags/{tag["id"]}')

        # After unbinding, no articles match
        resp = client.get(f'/articles?tag=Redis')
        assert len(resp.json['data']) == 0

    def test_filter_after_tag_rename(self, client):
        """After renaming a tag, filtering by the new name returns matching articles."""
        article = client.post('/articles', json={'title': 'Post', 'body': 'Content'}).json['data']
        tag = client.post('/tags', json={'name': 'OldName'}).json['data']

        client.post(f'/articles/{article["id"]}/tags', json={'tag_ids': [tag['id']]})

        # Rename the tag
        client.put(f'/tags/{tag["id"]}', json={'name': 'NewName'})

        # Old name should no longer match
        resp_old = client.get('/articles?tag=OldName')
        assert len(resp_old.json['data']) == 0

        # New name should match
        resp_new = client.get('/articles?tag=NewName')
        assert len(resp_new.json['data']) == 1
        assert resp_new.json['data'][0]['title'] == 'Post'

    def test_filter_after_tag_deletion(self, client):
        """After deleting a tag, filtering by that tag returns empty results."""
        article = client.post('/articles', json={'title': 'Post', 'body': 'Content'}).json['data']
        tag = client.post('/tags', json={'name': 'Temporary'}).json['data']

        client.post(f'/articles/{article["id"]}/tags', json={'tag_ids': [tag['id']]})
        client.delete(f'/tags/{tag["id"]}')

        # Filtering by deleted tag name returns empty
        resp = client.get('/articles?tag=Temporary')
        assert len(resp.json['data']) == 0

        # Filtering by deleted tag id returns empty
        resp = client.get(f'/articles?tag_id={tag["id"]}')
        assert len(resp.json['data']) == 0

    def test_filter_after_binding_second_tag(self, client):
        """After binding a second tag, filtering by either tag finds the article."""
        article = client.post('/articles', json={'title': 'Post', 'body': 'Content'}).json['data']
        t1 = client.post('/tags', json={'name': 'TagA'}).json['data']
        t2 = client.post('/tags', json={'name': 'TagB'}).json['data']

        client.post(f'/articles/{article["id"]}/tags', json={'tag_ids': [t1['id']]})
        assert len(client.get(f'/articles?tag=TagA').json['data']) == 1
        assert len(client.get(f'/articles?tag=TagB').json['data']) == 0

        # Bind second tag
        client.post(f'/articles/{article["id"]}/tags', json={'tag_ids': [t2['id']]})

        # Now both tags find the article
        assert len(client.get(f'/articles?tag=TagA').json['data']) == 1
        assert len(client.get(f'/articles?tag=TagB').json['data']) == 1


# ============================================================
# Boundary conditions
# ============================================================

class TestFilterBoundaryConditions:
    """Edge cases and boundary conditions for article filtering."""

    def test_filter_tag_name_with_special_characters(self, client):
        """Tag names with special characters should work for filtering."""
        tag = client.post('/tags', json={'name': 'C++'}).json['data']
        article = client.post('/articles', json={'title': 'C++ Guide', 'body': 'Content'}).json['data']
        client.post(f'/articles/{article["id"]}/tags', json={'tag_ids': [tag['id']]})

        resp = client.get('/articles?tag=C++')
        assert resp.status_code == 200
        assert len(resp.json['data']) == 1
        assert resp.json['data'][0]['title'] == 'C++ Guide'

    def test_filter_tag_name_with_spaces(self, client):
        """Tag names with spaces should work for filtering."""
        tag = client.post('/tags', json={'name': 'Machine Learning'}).json['data']
        article = client.post('/articles', json={'title': 'ML Intro', 'body': 'Content'}).json['data']
        client.post(f'/articles/{article["id"]}/tags', json={'tag_ids': [tag['id']]})

        resp = client.get('/articles?tag=Machine Learning')
        assert resp.status_code == 200
        assert len(resp.json['data']) == 1

    def test_filter_tag_name_with_unicode(self, client):
        """Tag names with unicode characters should work for filtering."""
        tag = client.post('/tags', json={'name': '数据库'}).json['data']
        article = client.post('/articles', json={'title': 'DB Post', 'body': 'Content'}).json['data']
        client.post(f'/articles/{article["id"]}/tags', json={'tag_ids': [tag['id']]})

        resp = client.get('/articles?tag=数据库')
        assert resp.status_code == 200
        assert len(resp.json['data']) == 1

    def test_filter_single_article_multiple_tags(self, client):
        """An article with multiple tags should appear when filtering by any of them."""
        article = client.post('/articles', json={'title': 'Multi', 'body': 'Content'}).json['data']
        t1 = client.post('/tags', json={'name': 'T1'}).json['data']
        t2 = client.post('/tags', json={'name': 'T2'}).json['data']
        t3 = client.post('/tags', json={'name': 'T3'}).json['data']

        client.post(f'/articles/{article["id"]}/tags', json={'tag_ids': [t1['id'], t2['id'], t3['id']]})

        for name in ('T1', 'T2', 'T3'):
            resp = client.get(f'/articles?tag={name}')
            assert len(resp.json['data']) == 1
            assert resp.json['data'][0]['title'] == 'Multi'

    def test_filter_many_articles_same_tag(self, client):
        """Multiple articles tagged with the same tag should all be returned."""
        tag = client.post('/tags', json={'name': 'Popular'}).json['data']

        for i in range(5):
            article = client.post('/articles', json={'title': f'Article {i}', 'body': f'Body {i}'}).json['data']
            client.post(f'/articles/{article["id"]}/tags', json={'tag_ids': [tag['id']]})

        resp = client.get('/articles?tag=Popular')
        assert resp.status_code == 200
        assert len(resp.json['data']) == 5

    def test_filter_tag_id_non_numeric(self, client):
        """Non-numeric tag_id should not crash; treat as no match."""
        resp = client.get('/articles?tag_id=abc')
        # Should not return 500; either 200 with empty data or 400/404
        assert resp.status_code in (200, 400, 404)

    def test_filter_tag_name_partial_match(self, client):
        """Partial tag name match should not return results (exact match only)."""
        tag = client.post('/tags', json={'name': 'JavaScript'}).json['data']
        article = client.post('/articles', json={'title': 'JS Post', 'body': 'Content'}).json['data']
        client.post(f'/articles/{article["id"]}/tags', json={'tag_ids': [tag['id']]})

        # Partial match should not work
        resp = client.get('/articles?tag=Java')
        assert len(resp.json['data']) == 0

    def test_filter_tag_name_whitespace_suffix(self, client):
        """Tag name with trailing whitespace should not match (exact match)."""
        tag = client.post('/tags', json={'name': 'Python'}).json['data']
        article = client.post('/articles', json={'title': 'Py Post', 'body': 'Content'}).json['data']
        client.post(f'/articles/{article["id"]}/tags', json={'tag_ids': [tag['id']]})

        # Query with trailing space should not match
        resp = client.get('/articles?tag=Python ')
        assert len(resp.json['data']) == 0

    def test_filter_when_tag_has_no_articles(self, client):
        """Filtering by a tag that exists but has no articles returns empty list."""
        tag = client.post('/tags', json={'name': 'Orphan'}).json['data']
        # Create an article but do not bind the tag
        client.post('/articles', json={'title': 'Some Post', 'body': 'Content'})

        resp = client.get(f'/articles?tag_id={tag["id"]}')
        assert resp.status_code == 200
        assert resp.json['data'] == []

    def test_filter_articles_order(self, client, seeded_data):
        """Filtered results should be ordered by article id (ascending)."""
        python_tag = [t for t in seeded_data['tags'] if t['name'] == 'Python'][0]
        resp = client.get(f'/articles?tag_id={python_tag["id"]}')
        ids = [a['id'] for a in resp.json['data']]
        assert ids == sorted(ids)


# ============================================================
# Response envelope validation
# ============================================================

class TestFilterResponseEnvelope:
    """Verify the response envelope structure is consistent."""

    def test_status_ok_on_match(self, client, seeded_data):
        """Successful filter with results returns status='ok'."""
        resp = client.get('/articles?tag=Python')
        assert resp.json['status'] == 'ok'

    def test_status_ok_on_no_match(self, client):
        """Filter with no results still returns status='ok'."""
        resp = client.get('/articles?tag=Nothing')
        assert resp.json['status'] == 'ok'

    def test_data_is_always_a_list(self, client, seeded_data):
        """The 'data' field is always a list, whether empty or populated."""
        resp_match = client.get('/articles?tag=Python')
        assert isinstance(resp_match.json['data'], list)

        resp_empty = client.get('/articles?tag=Nothing')
        assert isinstance(resp_empty.json['data'], list)

    def test_content_type_is_json(self, client, seeded_data):
        """Response content type should be application/json."""
        resp = client.get('/articles?tag=Python')
        assert resp.content_type == 'application/json'
