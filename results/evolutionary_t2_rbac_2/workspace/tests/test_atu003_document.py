"""
ATU-003 Document CRUD Routes - Unit Tests

Tests for the document_bp blueprint covering:
- GET    /documents        (list, tenant-scoped)
- GET    /documents/<id>   (single document)
- POST   /documents        (create)
- PUT    /documents/<id>   (update, owner or doc.write.any)
- DELETE /documents/<id>   (delete, tenant-scoped)

Seed data: two tenants, multiple users, permissions, and admin roles.
Tests build roles dynamically via the role management API to set up
different permission scenarios.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'starter'))

import pytest
from app import create_app, db
from models import Tenant, User, Role, Permission, Document, user_roles, role_permissions
from middleware import hash_password


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def client():
    """Create a test client with in-memory SQLite and seed data."""
    app = create_app()
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    app.config['JWT_SECRET'] = 'test-secret'

    with app.test_client() as c:
        with app.app_context():
            db.drop_all()
            db.create_all()

            # Tenants
            db.session.add(Tenant(id=1, name='TenantA'))
            db.session.add(Tenant(id=2, name='TenantB'))

            # Users (password: 'pw')
            pw = hash_password('pw')
            db.session.add(User(id=1, tenant_id=1, username='alice_admin', password_hash=pw))
            db.session.add(User(id=2, tenant_id=1, username='bob_editor', password_hash=pw))
            db.session.add(User(id=3, tenant_id=1, username='carol_viewer', password_hash=pw))
            db.session.add(User(id=4, tenant_id=1, username='dave_noroles', password_hash=pw))
            db.session.add(User(id=5, tenant_id=2, username='eve_b_admin', password_hash=pw))

            # Permissions
            perm_codes = [
                'doc.read', 'doc.write', 'doc.write.any',
                'doc.delete', 'role.manage',
            ]
            for code in perm_codes:
                db.session.add(Permission(code=code))
            db.session.flush()

            # Admin roles (all permissions)
            db.session.add(Role(id=1, tenant_id=1, name='super_admin'))
            db.session.add(Role(id=2, tenant_id=2, name='super_admin'))
            db.session.flush()

            # Assign all permissions to both admin roles
            db.session.execute(
                role_permissions.insert().from_select(
                    ['role_id', 'permission_id'],
                    db.session.query(db.literal(1), Permission.id).union_all(
                        db.session.query(db.literal(2), Permission.id)
                    ),
                )
            )

            # Assign admin roles
            db.session.execute(user_roles.insert().values(user_id=1, role_id=1))
            db.session.execute(user_roles.insert().values(user_id=5, role_id=2))

            db.session.commit()

        yield c


@pytest.fixture
def admin_token(client):
    return _login(client, 'alice_admin')


@pytest.fixture
def tenant_b_admin_token(client):
    return _login(client, 'eve_b_admin')


@pytest.fixture
def noroles_token(client):
    return _login(client, 'dave_noroles')


# ============================================================
# Helpers
# ============================================================


def _login(client, username):
    resp = client.post('/login', json={'username': username, 'password': 'pw'})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    return resp.json['data']['token']


def _auth(token):
    return {'Authorization': f'Bearer {token}'}


def _create_role(client, admin_token, name, permissions, parent_role_id=None):
    body = {'name': name, 'permissions': permissions}
    if parent_role_id is not None:
        body['parent_role_id'] = parent_role_id
    return client.post('/roles', json=body, headers=_auth(admin_token))


def _assign_role(client, admin_token, user_id, role_name):
    """Create a role and assign it to a user. Returns the role id."""
    roles_resp = client.get('/roles', headers=_auth(admin_token)).json['data']
    role_id = next(r['id'] for r in roles_resp if r['name'] == role_name)
    client.post(
        f'/users/{user_id}/roles',
        json={'role_id': role_id},
        headers=_auth(admin_token),
    )
    return role_id


def _create_document(client, token, title='Test Doc', content='Hello'):
    return client.post(
        '/documents',
        json={'title': title, 'content': content},
        headers=_auth(token),
    )


# ============================================================
# GET /documents - List documents
# ============================================================


class TestListDocuments:
    """Tests for GET /documents endpoint."""

    def test_list_documents_returns_200_with_own_tenant_only(self, client, admin_token, tenant_b_admin_token):
        """Successful list returns 200 and only documents from the caller's tenant."""
        _create_document(client, admin_token, title='a-doc', content='content-a')
        _create_document(client, tenant_b_admin_token, title='b-doc', content='content-b')

        resp = client.get('/documents', headers=_auth(admin_token))
        assert resp.status_code == 200
        data = resp.json['data']
        titles = [d['title'] for d in data]
        assert 'a-doc' in titles
        assert 'b-doc' not in titles

    def test_list_documents_no_doc_read_returns_403(self, client, noroles_token):
        """User without doc.read permission gets 403."""
        resp = client.get('/documents', headers=_auth(noroles_token))
        assert resp.status_code == 403

    def test_list_documents_response_format(self, client, admin_token):
        """Response follows the expected format with id, tenant_id, owner_id, title, content."""
        _create_document(client, admin_token, title='fmt-doc', content='fmt-content')

        resp = client.get('/documents', headers=_auth(admin_token))
        assert resp.status_code == 200
        assert resp.json['status'] == 'ok'
        data = resp.json['data']
        assert isinstance(data, list)
        doc = data[0]
        assert 'id' in doc
        assert 'tenant_id' in doc
        assert 'owner_id' in doc
        assert 'title' in doc
        assert 'content' in doc


# ============================================================
# GET /documents/<id> - Get single document
# ============================================================


class TestGetDocument:
    """Tests for GET /documents/<id> endpoint."""

    def test_get_document_returns_200(self, client, admin_token):
        """Successfully retrieve a document by ID returns 200."""
        create_resp = _create_document(client, admin_token, title='single-doc', content='single-content')
        doc_id = create_resp.json['data']['id']

        resp = client.get(f'/documents/{doc_id}', headers=_auth(admin_token))
        assert resp.status_code == 200
        assert resp.json['data']['title'] == 'single-doc'
        assert resp.json['data']['content'] == 'single-content'

    def test_get_document_not_found_returns_404(self, client, admin_token):
        """Non-existent document ID returns 404."""
        resp = client.get('/documents/99999', headers=_auth(admin_token))
        assert resp.status_code == 404

    def test_get_document_cross_tenant_returns_404(self, client, admin_token, tenant_b_admin_token):
        """Accessing a document from another tenant returns 404."""
        create_resp = _create_document(client, admin_token, title='a-only', content='secret')
        doc_id = create_resp.json['data']['id']

        resp = client.get(f'/documents/{doc_id}', headers=_auth(tenant_b_admin_token))
        assert resp.status_code == 404

    def test_get_document_no_doc_read_returns_403(self, client, noroles_token):
        """User without doc.read permission gets 403 even with valid document ID."""
        resp = client.get('/documents/1', headers=_auth(noroles_token))
        assert resp.status_code == 403


# ============================================================
# POST /documents - Create document
# ============================================================


class TestCreateDocument:
    """Tests for POST /documents endpoint."""

    def test_create_document_returns_201(self, client, admin_token):
        """Successfully create a document returns 201."""
        resp = _create_document(client, admin_token, title='new-doc', content='new-content')
        assert resp.status_code == 201
        data = resp.json['data']
        assert data['title'] == 'new-doc'
        assert data['content'] == 'new-content'

    def test_create_document_sets_tenant_id_from_jwt(self, client, admin_token, tenant_b_admin_token):
        """Created document's tenant_id matches the user's tenant from JWT."""
        resp_a = _create_document(client, admin_token, title='a-tenant-doc', content='')
        resp_b = _create_document(client, tenant_b_admin_token, title='b-tenant-doc', content='')

        assert resp_a.json['data']['tenant_id'] == 1
        assert resp_b.json['data']['tenant_id'] == 2

    def test_create_document_sets_owner_id_to_current_user(self, client, admin_token):
        """Created document's owner_id equals the authenticated user's ID."""
        resp = _create_document(client, admin_token, title='my-doc', content='')
        assert resp.json['data']['owner_id'] == 1  # alice_admin has id=1

    def test_create_document_no_doc_write_returns_403(self, client, admin_token):
        """User with only doc.read cannot create documents (403)."""
        _create_role(client, admin_token, 'reader_only', ['doc.read'])
        _assign_role(client, admin_token, 4, 'reader_only')
        noroles_token = _login(client, 'dave_noroles')

        resp = _create_document(client, noroles_token, title='forbidden', content='')
        assert resp.status_code == 403

    def test_create_document_response_has_id(self, client, admin_token):
        """Response includes a valid integer id for the new document."""
        resp = _create_document(client, admin_token, title='id-check', content='')
        assert 'id' in resp.json['data']
        assert isinstance(resp.json['data']['id'], int)


# ============================================================
# PUT /documents/<id> - Update document
# ============================================================


class TestUpdateDocument:
    """Tests for PUT /documents/<id> endpoint."""

    def test_update_own_document_returns_200(self, client, admin_token):
        """Owner with doc.write can update their own document."""
        create_resp = _create_document(client, admin_token, title='original', content='original-content')
        doc_id = create_resp.json['data']['id']

        resp = client.put(
            f'/documents/{doc_id}',
            json={'title': 'updated', 'content': 'updated-content'},
            headers=_auth(admin_token),
        )
        assert resp.status_code == 200
        assert resp.json['data']['title'] == 'updated'
        assert resp.json['data']['content'] == 'updated-content'

    def test_update_others_document_without_write_any_returns_403(self, client, admin_token):
        """User with doc.write but not doc.write.any cannot update another user's document."""
        # Create editor role with doc.read + doc.write (no doc.write.any)
        _create_role(client, admin_token, 'editor', ['doc.read', 'doc.write'])
        _assign_role(client, admin_token, 2, 'editor')  # bob_editor
        bob_token = _login(client, 'bob_editor')

        # Admin creates a document
        create_resp = _create_document(client, admin_token, title='admin-doc', content='x')
        doc_id = create_resp.json['data']['id']

        # Bob tries to update admin's document
        resp = client.put(
            f'/documents/{doc_id}',
            json={'title': 'hacked'},
            headers=_auth(bob_token),
        )
        assert resp.status_code == 403

    def test_update_others_document_with_write_any_returns_200(self, client, admin_token):
        """User with doc.write.any can update another user's document."""
        # Create a super-editor role with doc.write.any
        _create_role(client, admin_token, 'super_editor', ['doc.read', 'doc.write', 'doc.write.any'])
        _assign_role(client, admin_token, 2, 'super_editor')  # bob_editor
        bob_token = _login(client, 'bob_editor')

        # Admin creates a document
        create_resp = _create_document(client, admin_token, title='admin-doc2', content='x')
        doc_id = create_resp.json['data']['id']

        # Bob updates admin's document using doc.write.any
        resp = client.put(
            f'/documents/{doc_id}',
            json={'title': 'bob-edited'},
            headers=_auth(bob_token),
        )
        assert resp.status_code == 200
        assert resp.json['data']['title'] == 'bob-edited'

    def test_update_nonexistent_document_returns_404(self, client, admin_token):
        """Updating a non-existent document returns 404."""
        resp = client.put(
            '/documents/99999',
            json={'title': 'ghost', 'content': 'none'},
            headers=_auth(admin_token),
        )
        assert resp.status_code == 404


# ============================================================
# DELETE /documents/<id> - Delete document
# ============================================================


class TestDeleteDocument:
    """Tests for DELETE /documents/<id> endpoint."""

    def test_delete_document_returns_200(self, client, admin_token):
        """Successfully delete a document returns 200."""
        create_resp = _create_document(client, admin_token, title='to-delete', content='')
        doc_id = create_resp.json['data']['id']

        resp = client.delete(f'/documents/{doc_id}', headers=_auth(admin_token))
        assert resp.status_code == 200

        # Verify it's gone
        get_resp = client.get(f'/documents/{doc_id}', headers=_auth(admin_token))
        assert get_resp.status_code == 404

    def test_delete_document_no_doc_delete_returns_403(self, client, admin_token):
        """User without doc.delete permission gets 403."""
        _create_role(client, admin_token, 'writer_no_delete', ['doc.read', 'doc.write'])
        _assign_role(client, admin_token, 4, 'writer_no_delete')
        token = _login(client, 'dave_noroles')

        create_resp = _create_document(client, admin_token, title='admin-owned', content='')
        doc_id = create_resp.json['data']['id']

        resp = client.delete(f'/documents/{doc_id}', headers=_auth(token))
        assert resp.status_code == 403

    def test_delete_document_cross_tenant_returns_404(self, client, admin_token, tenant_b_admin_token):
        """Deleting a document from another tenant returns 404."""
        create_resp = _create_document(client, admin_token, title='a-only-del', content='')
        doc_id = create_resp.json['data']['id']

        resp = client.delete(f'/documents/{doc_id}', headers=_auth(tenant_b_admin_token))
        assert resp.status_code == 404

    def test_delete_nonexistent_document_returns_404(self, client, admin_token):
        """Deleting a non-existent document returns 404."""
        resp = client.delete('/documents/99999', headers=_auth(admin_token))
        assert resp.status_code == 404


# ============================================================
# End-to-end integration scenario
# ============================================================


class TestDocumentFullWorkflow:
    """End-to-end test: create role, assign, login, and exercise all document CRUD."""

    def test_full_crud_workflow(self, client, admin_token):
        """A user with doc.read, doc.write, doc.delete can list, create, get,
        update own, but cannot update others' documents."""
        # Setup: give bob all doc permissions except doc.write.any
        _create_role(client, admin_token, 'full_editor', ['doc.read', 'doc.write', 'doc.delete'])
        _assign_role(client, admin_token, 2, 'full_editor')
        bob_token = _login(client, 'bob_editor')

        # Create a document as bob
        create_resp = _create_document(client, bob_token, title='bob-workflow-doc', content='initial')
        assert create_resp.status_code == 201
        doc_id = create_resp.json['data']['id']
        assert create_resp.json['data']['owner_id'] == 2
        assert create_resp.json['data']['tenant_id'] == 1

        # List documents - bob's doc should appear
        list_resp = client.get('/documents', headers=_auth(bob_token))
        assert list_resp.status_code == 200
        assert any(d['id'] == doc_id for d in list_resp.json['data'])

        # Get single document
        get_resp = client.get(f'/documents/{doc_id}', headers=_auth(bob_token))
        assert get_resp.status_code == 200
        assert get_resp.json['data']['title'] == 'bob-workflow-doc'

        # Update own document
        update_resp = client.put(
            f'/documents/{doc_id}',
            json={'title': 'bob-updated-doc', 'content': 'updated'},
            headers=_auth(bob_token),
        )
        assert update_resp.status_code == 200
        assert update_resp.json['data']['title'] == 'bob-updated-doc'

        # Admin creates a document, bob tries to update it (no doc.write.any)
        admin_doc = _create_document(client, admin_token, title='admin-secret', content='')
        admin_doc_id = admin_doc.json['data']['id']
        forbidden = client.put(
            f'/documents/{admin_doc_id}',
            json={'title': 'hacked-by-bob'},
            headers=_auth(bob_token),
        )
        assert forbidden.status_code == 403

        # Delete own document
        delete_resp = client.delete(f'/documents/{doc_id}', headers=_auth(bob_token))
        assert delete_resp.status_code == 200

        # Confirm deletion
        gone = client.get(f'/documents/{doc_id}', headers=_auth(bob_token))
        assert gone.status_code == 404
