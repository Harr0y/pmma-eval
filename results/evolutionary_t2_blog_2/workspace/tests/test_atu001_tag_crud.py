"""
ATU-001: Tag CRUD Routes -- complete unit tests.

Covers all four endpoints on tag_bp with normal flows, error cases,
and edge conditions.
"""

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'starter'))

from app import create_app, db
from models import Article, Tag


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
def existing_tag(client):
    """Insert one tag and return its id."""
    resp = client.post('/tags', json={'name': 'Python'})
    return resp.json['data']['id']


@pytest.fixture
def existing_tag_with_article(client):
    """Insert a tag bound to an article and return (tag_id, article_id)."""
    a_resp = client.post('/articles', json={'title': 'Blog', 'body': 'Content'})
    article_id = a_resp.json['data']['id']
    t_resp = client.post('/tags', json={'name': 'Python'})
    tag_id = t_resp.json['data']['id']
    client.post(f'/articles/{article_id}/tags', json={'tag_ids': [tag_id]})
    return tag_id, article_id


# ---------------------------------------------------------------------------
# POST /tags -- Create tag
# ---------------------------------------------------------------------------

class TestCreateTag:

    def test_create_tag_success(self, client):
        """Successful creation returns 201 with id and name."""
        resp = client.post('/tags', json={'name': 'Python'})
        assert resp.status_code == 201
        data = resp.json['data']
        assert 'id' in data
        assert data['name'] == 'Python'
        assert resp.json['status'] == 'ok'

    def test_create_tag_returns_integer_id(self, client):
        """The returned id must be an integer."""
        resp = client.post('/tags', json={'name': 'Flask'})
        assert isinstance(resp.json['data']['id'], int)

    def test_create_tag_missing_name(self, client):
        """Missing name field returns 400."""
        resp = client.post('/tags', json={})
        assert resp.status_code == 400
        assert resp.json['status'] == 'error'

    def test_create_tag_null_name(self, client):
        """Explicit null name returns 400."""
        resp = client.post('/tags', json={'name': None})
        assert resp.status_code == 400

    def test_create_tag_empty_name(self, client):
        """Empty string name returns 400."""
        resp = client.post('/tags', json={'name': ''})
        assert resp.status_code == 400

    def test_create_tag_whitespace_only_name(self, client):
        """Whitespace-only name returns 400."""
        resp = client.post('/tags', json={'name': '   '})
        assert resp.status_code == 400

    def test_create_tag_duplicate_name(self, client):
        """Duplicate tag name returns 409."""
        client.post('/tags', json={'name': 'Python'})
        resp = client.post('/tags', json={'name': 'Python'})
        assert resp.status_code == 409
        assert resp.json['status'] == 'error'

    def test_create_tag_duplicate_case_sensitive(self, client):
        """Tag names with different casing are treated as distinct (DB unique)."""
        client.post('/tags', json={'name': 'Python'})
        resp = client.post('/tags', json={'name': 'python'})
        # Depending on collation this may succeed or conflict.
        # We only assert the response is well-formed (either 201 or 409).
        assert resp.status_code in (201, 409)

    def test_create_tag_auto_increment_id(self, client):
        """Consecutive tags have incrementing ids."""
        r1 = client.post('/tags', json={'name': 'TagA'})
        r2 = client.post('/tags', json={'name': 'TagB'})
        assert r2.json['data']['id'] == r1.json['data']['id'] + 1

    def test_create_tag_no_extra_body_fields(self, client):
        """Extra fields in the request body should be ignored."""
        resp = client.post('/tags', json={'name': 'Flask', 'color': 'blue'})
        assert resp.status_code == 201
        assert resp.json['data']['name'] == 'Flask'
        # Only id and name are expected in data
        assert set(resp.json['data'].keys()) == {'id', 'name'}


# ---------------------------------------------------------------------------
# GET /tags -- List all tags
# ---------------------------------------------------------------------------

class TestListTags:

    def test_list_tags_empty(self, client):
        """Empty database returns an empty list."""
        resp = client.get('/tags')
        assert resp.status_code == 200
        assert resp.json['status'] == 'ok'
        assert resp.json['data'] == []

    def test_list_tags_single(self, client):
        """One tag is returned."""
        client.post('/tags', json={'name': 'Python'})
        resp = client.get('/tags')
        assert resp.status_code == 200
        assert len(resp.json['data']) == 1
        assert resp.json['data'][0]['name'] == 'Python'

    def test_list_tags_multiple(self, client):
        """All created tags are returned."""
        for name in ('Python', 'Flask', 'SQLAlchemy'):
            client.post('/tags', json={'name': name})
        resp = client.get('/tags')
        assert resp.status_code == 200
        assert len(resp.json['data']) == 3
        names = {t['name'] for t in resp.json['data']}
        assert names == {'Python', 'Flask', 'SQLAlchemy'}

    def test_list_tags_structure(self, client):
        """Each tag in the list has id (int) and name (str)."""
        client.post('/tags', json={'name': 'Flask'})
        resp = client.get('/tags')
        tag = resp.json['data'][0]
        assert isinstance(tag['id'], int)
        assert isinstance(tag['name'], str)
        assert set(tag.keys()) == {'id', 'name'}

    def test_list_tags_after_deletion(self, client):
        """Deleted tags should no longer appear in the list."""
        r = client.post('/tags', json={'name': 'Temp'})
        tid = r.json['data']['id']
        client.delete(f'/tags/{tid}')
        resp = client.get('/tags')
        assert len(resp.json['data']) == 0

    def test_list_tags_after_rename(self, client):
        """Renamed tag reflects the new name."""
        r = client.post('/tags', json={'name': 'OldName'})
        tid = r.json['data']['id']
        client.put(f'/tags/{tid}', json={'name': 'NewName'})
        resp = client.get('/tags')
        assert resp.json['data'][0]['name'] == 'NewName'


# ---------------------------------------------------------------------------
# PUT /tags/<id> -- Update tag name
# ---------------------------------------------------------------------------

class TestUpdateTag:

    def test_update_tag_success(self, client, existing_tag):
        """Successful update returns 200 with updated data."""
        resp = client.put(f'/tags/{existing_tag}', json={'name': 'Java'})
        assert resp.status_code == 200
        assert resp.json['status'] == 'ok'
        assert resp.json['data']['id'] == existing_tag
        assert resp.json['data']['name'] == 'Java'

    def test_update_tag_missing_name(self, client, existing_tag):
        """Missing name field returns 400."""
        resp = client.put(f'/tags/{existing_tag}', json={})
        assert resp.status_code == 400
        assert resp.json['status'] == 'error'

    def test_update_tag_null_name(self, client, existing_tag):
        """Null name returns 400."""
        resp = client.put(f'/tags/{existing_tag}', json={'name': None})
        assert resp.status_code == 400

    def test_update_tag_empty_name(self, client, existing_tag):
        """Empty name returns 400."""
        resp = client.put(f'/tags/{existing_tag}', json={'name': ''})
        assert resp.status_code == 400

    def test_update_tag_whitespace_only_name(self, client, existing_tag):
        """Whitespace-only name returns 400."""
        resp = client.put(f'/tags/{existing_tag}', json={'name': '   '})
        assert resp.status_code == 400

    def test_update_tag_duplicate_name(self, client):
        """Renaming to an already-existing name returns 409."""
        r1 = client.post('/tags', json={'name': 'Python'})
        r2 = client.post('/tags', json={'name': 'Flask'})
        resp = client.put(f'/tags/{r2.json["data"]["id"]}', json={'name': 'Python'})
        assert resp.status_code == 409
        assert resp.json['status'] == 'error'

    def test_update_tag_not_found(self, client):
        """Updating a non-existent tag returns 404."""
        resp = client.put('/tags/9999', json={'name': 'Nope'})
        assert resp.status_code == 404
        assert resp.json['status'] == 'error'

    def test_update_tag_same_name_noop(self, client, existing_tag):
        """Updating a tag to its current name should succeed (no-op)."""
        resp = client.put(f'/tags/{existing_tag}', json={'name': 'Python'})
        assert resp.status_code == 200
        assert resp.json['data']['name'] == 'Python'

    def test_update_tag_id_preserved(self, client, existing_tag):
        """The tag id must not change after an update."""
        resp = client.put(f'/tags/{existing_tag}', json={'name': 'Golang'})
        assert resp.json['data']['id'] == existing_tag

    def test_update_tag_reflected_in_list(self, client, existing_tag):
        """After renaming, GET /tags shows the new name."""
        client.put(f'/tags/{existing_tag}', json={'name': 'Rust'})
        resp = client.get('/tags')
        assert resp.json['data'][0]['name'] == 'Rust'


# ---------------------------------------------------------------------------
# DELETE /tags/<id> -- Delete tag
# ---------------------------------------------------------------------------

class TestDeleteTag:

    def test_delete_tag_success(self, client, existing_tag):
        """Successful deletion returns 200 with confirmation message."""
        resp = client.delete(f'/tags/{existing_tag}')
        assert resp.status_code == 200
        assert resp.json['status'] == 'ok'
        assert resp.json['data']['message'] == 'Tag deleted'

    def test_delete_tag_not_found(self, client):
        """Deleting a non-existent tag returns 404."""
        resp = client.delete('/tags/9999')
        assert resp.status_code == 404
        assert resp.json['status'] == 'error'

    def test_delete_tag_removes_from_list(self, client, existing_tag):
        """Deleted tag no longer appears in the tag list."""
        client.delete(f'/tags/{existing_tag}')
        resp = client.get('/tags')
        assert len(resp.json['data']) == 0

    def test_delete_tag_cascades_bindings(self, client, existing_tag_with_article):
        """Deleting a tag removes its association with articles."""
        tag_id, article_id = existing_tag_with_article
        client.delete(f'/tags/{tag_id}')
        resp = client.get(f'/articles/{article_id}/tags')
        assert resp.status_code == 200
        assert len(resp.json['data']) == 0

    def test_delete_tag_does_not_delete_article(self, client, existing_tag_with_article):
        """Deleting a tag must not delete the article itself."""
        tag_id, article_id = existing_tag_with_article
        client.delete(f'/tags/{tag_id}')
        resp = client.get(f'/articles/{article_id}')
        assert resp.status_code == 200
        assert resp.json['data']['title'] == 'Blog'

    def test_delete_tag_idempotent(self, client, existing_tag):
        """Deleting an already-deleted tag returns 404 (not 500)."""
        client.delete(f'/tags/{existing_tag}')
        resp = client.delete(f'/tags/{existing_tag}')
        assert resp.status_code == 404

    def test_delete_one_tag_does_not_affect_other(self, client):
        """Deleting one tag leaves other tags intact."""
        r1 = client.post('/tags', json={'name': 'Keep'})
        r2 = client.post('/tags', json={'name': 'Remove'})
        client.delete(f'/tags/{r2.json["data"]["id"]}')
        resp = client.get('/tags')
        assert len(resp.json['data']) == 1
        assert resp.json['data'][0]['name'] == 'Keep'


# ---------------------------------------------------------------------------
# Cross-endpoint consistency
# ---------------------------------------------------------------------------

class TestCrossEndpointConsistency:

    def test_create_then_get(self, client):
        """A tag created via POST appears in GET /tags."""
        created = client.post('/tags', json={'name': 'Django'}).json['data']
        listed = client.get('/tags').json['data']
        assert len(listed) == 1
        assert listed[0]['id'] == created['id']
        assert listed[0]['name'] == created['name']

    def test_create_update_then_get(self, client):
        """Create, rename, then GET reflects the rename."""
        created = client.post('/tags', json={'name': 'Old'}).json['data']
        client.put(f'/tags/{created["id"]}', json={'name': 'New'})
        listed = client.get('/tags').json['data']
        assert listed[0]['name'] == 'New'
        assert listed[0]['id'] == created['id']

    def test_create_delete_then_get(self, client):
        """Create then DELETE means GET returns empty list."""
        created = client.post('/tags', json={'name': 'Gone'}).json['data']
        client.delete(f'/tags/{created["id"]}')
        listed = client.get('/tags').json['data']
        assert listed == []

    def test_response_status_field(self, client):
        """All successful responses include status='ok'."""
        r_create = client.post('/tags', json={'name': 'Test'})
        assert r_create.json['status'] == 'ok'

        r_list = client.get('/tags')
        assert r_list.json['status'] == 'ok'

        tid = r_create.json['data']['id']
        r_update = client.put(f'/tags/{tid}', json={'name': 'Updated'})
        assert r_update.json['status'] == 'ok'

        r_delete = client.delete(f'/tags/{tid}')
        assert r_delete.json['status'] == 'ok'

    def test_response_status_field_errors(self, client):
        """All error responses include status='error'."""
        r_missing = client.post('/tags', json={})
        assert r_missing.json['status'] == 'error'

        r_notfound = client.put('/tags/9999', json={'name': 'X'})
        assert r_notfound.json['status'] == 'error'

        r_del_notfound = client.delete('/tags/9999')
        assert r_del_notfound.json['status'] == 'error'
