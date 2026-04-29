"""
ATU-002: Article Basic CRUD -- complete unit tests.

Covers three endpoints on article_bp:
  - POST   /articles        -> Create article
  - GET    /articles        -> List all articles
  - GET    /articles/<id>   -> Get single article

Normal flows, error cases, and edge conditions are included.
Tag-related behaviour is intentionally out of scope.
"""

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'starter'))

from app import create_app, db
from models import Article


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

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
def existing_article(client):
    """Insert one article via API and return its id."""
    resp = client.post('/articles', json={'title': 'Sample', 'body': 'Content'})
    return resp.json['data']['id']


@pytest.fixture
def multiple_articles(client):
    """Insert three articles and return a list of their ids."""
    ids = []
    for title, body in [('First', 'Body1'), ('Second', 'Body2'), ('Third', 'Body3')]:
        resp = client.post('/articles', json={'title': title, 'body': body})
        ids.append(resp.json['data']['id'])
    return ids


# ---------------------------------------------------------------------------
# POST /articles -- Create article
# ---------------------------------------------------------------------------

class TestCreateArticle:

    def test_create_article_success(self, client):
        """Successful creation returns 201 with id, title, and body."""
        resp = client.post('/articles', json={'title': 'Hello', 'body': 'World'})
        assert resp.status_code == 201
        assert resp.json['status'] == 'ok'
        data = resp.json['data']
        assert 'id' in data
        assert data['title'] == 'Hello'
        assert data['body'] == 'World'

    def test_create_article_returns_integer_id(self, client):
        """The returned id must be an integer."""
        resp = client.post('/articles', json={'title': 'Title', 'body': 'Body'})
        assert isinstance(resp.json['data']['id'], int)

    def test_create_article_data_keys(self, client):
        """Response data contains exactly id, title, and body."""
        resp = client.post('/articles', json={'title': 'T', 'body': 'B'})
        assert set(resp.json['data'].keys()) == {'id', 'title', 'body'}

    def test_create_article_auto_increment_id(self, client):
        """Consecutive articles have incrementing ids."""
        r1 = client.post('/articles', json={'title': 'A1', 'body': 'B1'})
        r2 = client.post('/articles', json={'title': 'A2', 'body': 'B2'})
        assert r2.json['data']['id'] == r1.json['data']['id'] + 1

    def test_create_article_missing_title(self, client):
        """Missing title field returns 400."""
        resp = client.post('/articles', json={'body': 'OnlyBody'})
        assert resp.status_code == 400
        assert resp.json['status'] == 'error'

    def test_create_article_missing_body(self, client):
        """Missing body field returns 400."""
        resp = client.post('/articles', json={'title': 'OnlyTitle'})
        assert resp.status_code == 400
        assert resp.json['status'] == 'error'

    def test_create_article_missing_both_fields(self, client):
        """Missing both title and body returns 400."""
        resp = client.post('/articles', json={})
        assert resp.status_code == 400
        assert resp.json['status'] == 'error'

    def test_create_article_null_title(self, client):
        """Explicit null title returns 400."""
        resp = client.post('/articles', json={'title': None, 'body': 'Body'})
        assert resp.status_code == 400

    def test_create_article_null_body(self, client):
        """Explicit null body returns 400."""
        resp = client.post('/articles', json={'title': 'Title', 'body': None})
        assert resp.status_code == 400

    def test_create_article_empty_title(self, client):
        """Empty string title returns 400."""
        resp = client.post('/articles', json={'title': '', 'body': 'Body'})
        assert resp.status_code == 400

    def test_create_article_empty_body(self, client):
        """Empty string body returns 400."""
        resp = client.post('/articles', json={'title': 'Title', 'body': ''})
        assert resp.status_code == 400

    def test_create_article_whitespace_only_title(self, client):
        """Whitespace-only title returns 400."""
        resp = client.post('/articles', json={'title': '   ', 'body': 'Body'})
        assert resp.status_code == 400

    def test_create_article_whitespace_only_body(self, client):
        """Whitespace-only body returns 400."""
        resp = client.post('/articles', json={'title': 'Title', 'body': '   '})
        assert resp.status_code == 400

    def test_create_article_extra_fields_ignored(self, client):
        """Extra fields in the request body should be ignored."""
        resp = client.post('/articles', json={
            'title': 'Title', 'body': 'Body', 'author': 'Alice', 'tags': [1, 2]
        })
        assert resp.status_code == 201
        data = resp.json['data']
        assert set(data.keys()) == {'id', 'title', 'body'}
        assert data['title'] == 'Title'
        assert data['body'] == 'Body'

    def test_create_article_long_title(self, client):
        """A very long title (close to 200 char limit) should succeed."""
        long_title = 'A' * 199
        resp = client.post('/articles', json={'title': long_title, 'body': 'Body'})
        assert resp.status_code == 201
        assert resp.json['data']['title'] == long_title

    def test_create_article_long_body(self, client):
        """A very long body should succeed."""
        long_body = 'X' * 10000
        resp = client.post('/articles', json={'title': 'Title', 'body': long_body})
        assert resp.status_code == 201
        assert resp.json['data']['body'] == long_body

    def test_create_article_unicode_title_and_body(self, client):
        """Unicode characters in title and body should work."""
        resp = client.post('/articles', json={'title': '你好世界', 'body': '本文内容'})
        assert resp.status_code == 201
        assert resp.json['data']['title'] == '你好世界'
        assert resp.json['data']['body'] == '本文内容'

    def test_create_article_special_characters(self, client):
        """Special characters (HTML-like, markdown) should be stored as-is."""
        resp = client.post('/articles', json={
            'title': '<script>alert("xss")</script>',
            'body': '# Header\n**bold**'
        })
        assert resp.status_code == 201
        assert '<script>' in resp.json['data']['title']
        assert '**bold**' in resp.json['data']['body']

    def test_create_article_id_persists_in_db(self, client):
        """Created article is actually persisted and retrievable."""
        create_resp = client.post('/articles', json={'title': 'Persist', 'body': 'Test'})
        aid = create_resp.json['data']['id']
        get_resp = client.get(f'/articles/{aid}')
        assert get_resp.status_code == 200
        assert get_resp.json['data']['title'] == 'Persist'


# ---------------------------------------------------------------------------
# GET /articles -- List all articles
# ---------------------------------------------------------------------------

class TestListArticles:

    def test_list_articles_empty(self, client):
        """Empty database returns an empty list."""
        resp = client.get('/articles')
        assert resp.status_code == 200
        assert resp.json['status'] == 'ok'
        assert resp.json['data'] == []

    def test_list_articles_single(self, client):
        """One article is returned."""
        client.post('/articles', json={'title': 'Only', 'body': 'One'})
        resp = client.get('/articles')
        assert resp.status_code == 200
        assert len(resp.json['data']) == 1
        assert resp.json['data'][0]['title'] == 'Only'

    def test_list_articles_multiple(self, client, multiple_articles):
        """All created articles are returned."""
        resp = client.get('/articles')
        assert resp.status_code == 200
        assert len(resp.json['data']) == 3

    def test_list_articles_structure(self, client):
        """Each article in the list has id (int), title (str), body (str)."""
        client.post('/articles', json={'title': 'Struct', 'body': 'Check'})
        resp = client.get('/articles')
        article = resp.json['data'][0]
        assert isinstance(article['id'], int)
        assert isinstance(article['title'], str)
        assert isinstance(article['body'], str)
        assert set(article.keys()) == {'id', 'title', 'body'}

    def test_list_articles_order_matches_creation(self, client, multiple_articles):
        """Articles are listed in creation order (ascending id)."""
        resp = client.get('/articles')
        ids = [a['id'] for a in resp.json['data']]
        assert ids == sorted(ids)

    def test_list_articles_content_correct(self, client, multiple_articles):
        """Listed articles contain the correct title and body."""
        resp = client.get('/articles')
        titles = {a['title'] for a in resp.json['data']}
        bodies = {a['body'] for a in resp.json['data']}
        assert titles == {'First', 'Second', 'Third'}
        assert bodies == {'Body1', 'Body2', 'Body3'}

    def test_list_articles_many(self, client):
        """Listing many articles (20) works correctly."""
        for i in range(20):
            client.post('/articles', json={'title': f'T{i}', 'body': f'B{i}'})
        resp = client.get('/articles')
        assert resp.status_code == 200
        assert len(resp.json['data']) == 20

    def test_list_articles_after_create_and_get(self, client):
        """List reflects articles created and verified individually."""
        r1 = client.post('/articles', json={'title': 'A', 'body': 'B'})
        r2 = client.post('/articles', json={'title': 'C', 'body': 'D'})
        # Verify individual gets
        assert client.get(f'/articles/{r1.json["data"]["id"]}').json['data']['title'] == 'A'
        assert client.get(f'/articles/{r2.json["data"]["id"]}').json['data']['title'] == 'C'
        # List should show both
        resp = client.get('/articles')
        assert len(resp.json['data']) == 2


# ---------------------------------------------------------------------------
# GET /articles/<id> -- Get single article
# ---------------------------------------------------------------------------

class TestGetArticle:

    def test_get_article_success(self, client, existing_article):
        """Successful retrieval returns 200 with correct data."""
        resp = client.get(f'/articles/{existing_article}')
        assert resp.status_code == 200
        assert resp.json['status'] == 'ok'
        data = resp.json['data']
        assert data['id'] == existing_article
        assert data['title'] == 'Sample'
        assert data['body'] == 'Content'

    def test_get_article_data_keys(self, client, existing_article):
        """Response data contains exactly id, title, and body."""
        resp = client.get(f'/articles/{existing_article}')
        assert set(resp.json['data'].keys()) == {'id', 'title', 'body'}

    def test_get_article_id_type(self, client, existing_article):
        """Returned id is an integer."""
        resp = client.get(f'/articles/{existing_article}')
        assert isinstance(resp.json['data']['id'], int)

    def test_get_article_not_found(self, client):
        """Non-existent article id returns 404."""
        resp = client.get('/articles/9999')
        assert resp.status_code == 404
        assert resp.json['status'] == 'error'

    def test_get_article_zero_id(self, client):
        """Id 0 (no such row) returns 404."""
        resp = client.get('/articles/0')
        assert resp.status_code == 404

    def test_get_article_negative_id(self, client):
        """Negative id returns 404."""
        resp = client.get('/articles/-1')
        assert resp.status_code == 404

    def test_get_article_string_id(self, client):
        """Non-numeric id returns 404 (or 404/400)."""
        resp = client.get('/articles/abc')
        assert resp.status_code in (400, 404)

    def test_get_article_different_articles(self, client, multiple_articles):
        """Each id returns the correct article."""
        for aid in multiple_articles:
            resp = client.get(f'/articles/{aid}')
            assert resp.status_code == 200
            assert resp.json['data']['id'] == aid

    def test_get_article_consistency_after_creation(self, client):
        """GET returns the same data that was sent via POST."""
        post_resp = client.post('/articles', json={
            'title': 'Consistent', 'body': 'Data integrity check'
        })
        aid = post_resp.json['data']['id']
        get_resp = client.get(f'/articles/{aid}')
        assert get_resp.json['data']['title'] == 'Consistent'
        assert get_resp.json['data']['body'] == 'Data integrity check'

    def test_get_article_long_body(self, client):
        """Getting an article with a very long body works."""
        long_body = 'Paragraph. ' * 5000
        post_resp = client.post('/articles', json={'title': 'Long', 'body': long_body})
        aid = post_resp.json['data']['id']
        get_resp = client.get(f'/articles/{aid}')
        assert get_resp.status_code == 200
        assert get_resp.json['data']['body'] == long_body

    def test_get_article_unicode_content(self, client):
        """Getting an article with unicode content works."""
        post_resp = client.post('/articles', json={
            'title': '日本語テスト', 'body': '内容テスト'
        })
        aid = post_resp.json['data']['id']
        get_resp = client.get(f'/articles/{aid}')
        assert get_resp.json['data']['title'] == '日本語テスト'
        assert get_resp.json['data']['body'] == '内容テスト'


# ---------------------------------------------------------------------------
# Cross-endpoint consistency
# ---------------------------------------------------------------------------

class TestCrossEndpointConsistency:

    def test_create_then_get(self, client):
        """An article created via POST is retrievable by GET /articles/<id>."""
        created = client.post('/articles', json={'title': 'Cross1', 'body': 'B1'}).json['data']
        fetched = client.get(f'/articles/{created["id"]}').json['data']
        assert fetched['id'] == created['id']
        assert fetched['title'] == created['title']
        assert fetched['body'] == created['body']

    def test_create_then_list(self, client):
        """An article created via POST appears in GET /articles."""
        created = client.post('/articles', json={'title': 'Cross2', 'body': 'B2'}).json['data']
        listed = client.get('/articles').json['data']
        assert len(listed) == 1
        assert listed[0]['id'] == created['id']
        assert listed[0]['title'] == created['title']

    def test_list_and_get_consistent(self, client, multiple_articles):
        """GET /articles and GET /articles/<id> return the same data."""
        listed = client.get('/articles').json['data']
        for article in listed:
            fetched = client.get(f'/articles/{article["id"]}').json['data']
            assert fetched == article

    def test_response_status_field_success(self, client):
        """All successful responses include status='ok'."""
        r_create = client.post('/articles', json={'title': 'Status', 'body': 'Check'})
        assert r_create.json['status'] == 'ok'

        r_list = client.get('/articles')
        assert r_list.json['status'] == 'ok'

        aid = r_create.json['data']['id']
        r_get = client.get(f'/articles/{aid}')
        assert r_get.json['status'] == 'ok'

    def test_response_status_field_errors(self, client):
        """All error responses include status='error'."""
        r_missing_title = client.post('/articles', json={'body': 'NoTitle'})
        assert r_missing_title.json['status'] == 'error'

        r_missing_body = client.post('/articles', json={'title': 'NoBody'})
        assert r_missing_body.json['status'] == 'error'

        r_notfound = client.get('/articles/9999')
        assert r_notfound.json['status'] == 'error'

    def test_isolation_between_requests(self, client):
        """Each POST creates a separate, independent article."""
        r1 = client.post('/articles', json={'title': 'A', 'body': 'B'})
        r2 = client.post('/articles', json={'title': 'C', 'body': 'D'})
        assert r1.json['data']['id'] != r2.json['data']['id']

        g1 = client.get(f'/articles/{r1.json["data"]["id"]}').json['data']
        g2 = client.get(f'/articles/{r2.json["data"]["id"]}').json['data']
        assert g1['title'] == 'A'
        assert g2['title'] == 'C'

    def test_multiple_creates_all_in_list(self, client):
        """Multiple POST requests all appear in the list."""
        titles = [f'Article_{i}' for i in range(5)]
        for t in titles:
            client.post('/articles', json={'title': t, 'body': f'Body_{t}'})
        resp = client.get('/articles')
        assert resp.status_code == 200
        assert len(resp.json['data']) == 5
        returned_titles = {a['title'] for a in resp.json['data']}
        assert returned_titles == set(titles)
