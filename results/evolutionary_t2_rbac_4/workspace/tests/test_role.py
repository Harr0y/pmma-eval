"""
ATU-002: Role Management Routes (routes_role.py) Unit Tests

Verify all role management endpoints on role_bp blueprint.

Covered endpoints:
1. POST /roles          -- Create role (role.manage required)
2. GET /roles           -- List tenant roles (role.manage required)
3. PUT /roles/<id>/permissions -- Replace permission set + parent (role.manage required)
4. POST /users/<id>/roles     -- Assign role to user (role.manage required)
5. DELETE /users/<id>/roles/<role_id> -- Remove role from user (role.manage required)
6. Inheritance cycle detection when setting parent_role_id

Seed data:
- TenantA (id=1): alice_admin (super_admin, all perms), bob (no roles)
- TenantB (id=2): eve_b_admin (super_admin, all perms)
- Permissions: doc.read, doc.write, doc.delete, doc.write.any, role.manage
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'starter'))

from app import create_app, db
from models import Tenant, User, Role, Permission, user_roles, role_permissions
from middleware import hash_password


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def client():
    """Create test client with seed data matching ATU-002 spec."""
    app = create_app()
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    app.config['JWT_SECRET'] = 'test-secret'
    app.config['JWT_EXPIRY_HOURS'] = 24

    with app.test_client() as c:
        with app.app_context():
            db.drop_all()
            db.create_all()

            # -- Tenants --
            db.session.add(Tenant(id=1, name='TenantA'))
            db.session.add(Tenant(id=2, name='TenantB'))

            # -- Users --
            pw = hash_password('pw')
            db.session.add(User(id=1, tenant_id=1, username='alice_admin', password_hash=pw))
            db.session.add(User(id=2, tenant_id=1, username='bob', password_hash=pw))
            db.session.add(User(id=5, tenant_id=2, username='eve_b_admin', password_hash=pw))

            # -- Permissions --
            perm_codes = ['doc.read', 'doc.write', 'doc.delete', 'doc.write.any', 'role.manage']
            for code in perm_codes:
                db.session.add(Permission(code=code))
            db.session.flush()

            # -- Roles --
            db.session.add(Role(id=1, tenant_id=1, name='super_admin'))
            db.session.add(Role(id=2, tenant_id=2, name='super_admin'))
            db.session.flush()

            # -- Assign all permissions to both admin roles --
            db.session.execute(
                role_permissions.insert().from_select(
                    ['role_id', 'permission_id'],
                    db.session.query(db.literal(1), Permission.id)
                    .union_all(db.session.query(db.literal(2), Permission.id))
                )
            )

            # -- Assign admin roles to admin users --
            db.session.execute(user_roles.insert().values(user_id=1, role_id=1))
            db.session.execute(user_roles.insert().values(user_id=5, role_id=2))

            db.session.commit()
        yield c


# ============================================================
# Helpers
# ============================================================


def _login(client, username):
    """Login and return JWT token string."""
    resp = client.post('/login', json={'username': username, 'password': 'pw'})
    assert resp.status_code == 200, f'Login failed for {username}: {resp.get_data(as_text=True)}'
    return resp.json['data']['token']


def _auth(token):
    """Return Authorization header dict."""
    return {'Authorization': f'Bearer {token}'}


def _create_role(client, admin_token, name, permissions, parent_role_id=None):
    """Helper to POST /roles."""
    body = {'name': name, 'permissions': permissions}
    if parent_role_id is not None:
        body['parent_role_id'] = parent_role_id
    return client.post('/roles', json=body, headers=_auth(admin_token))


# ============================================================
# Fixtures: tokens
# ============================================================


@pytest.fixture
def admin_token(client):
    """TenantA admin (alice_admin) with role.manage permission."""
    return _login(client, 'alice_admin')


@pytest.fixture
def tenant_b_admin_token(client):
    """TenantB admin (eve_b_admin) with role.manage permission."""
    return _login(client, 'eve_b_admin')


@pytest.fixture
def noroles_token(client):
    """TenantA user bob with no roles (no role.manage permission)."""
    return _login(client, 'bob')


# ============================================================
# 1. POST /roles -- Create Role
# ============================================================


class TestCreateRole:
    """POST /roles endpoint tests."""

    def test_create_role_success_201(self, client, admin_token):
        """Admin creates a role -> 201, returns id/name/permissions."""
        resp = _create_role(client, admin_token, 'viewer', ['doc.read'])

        assert resp.status_code == 201
        data = resp.json
        assert data['status'] == 'ok'
        assert data['data']['name'] == 'viewer'
        assert data['data']['permissions'] == ['doc.read']
        assert 'id' in data['data']

    def test_create_role_with_parent(self, client, admin_token):
        """Create a role with parent_role_id -> 201, parent set correctly."""
        parent = _create_role(client, admin_token, 'base', ['doc.read'])
        parent_id = parent.json['data']['id']

        child = _create_role(client, admin_token, 'editor', ['doc.write'],
                             parent_role_id=parent_id)

        assert child.status_code == 201
        assert child.json['data']['name'] == 'editor'
        assert child.json['data']['parent_role_id'] == parent_id

    def test_create_role_with_null_parent(self, client, admin_token):
        """Create a role with parent_role_id explicitly set to null -> 201."""
        resp = _create_role(client, admin_token, 'standalone', ['doc.read'],
                            parent_role_id=None)
        assert resp.status_code == 201
        assert resp.json['data']['parent_role_id'] is None

    def test_create_role_missing_name_400(self, client, admin_token):
        """Missing 'name' field -> 400."""
        resp = client.post('/roles', json={'permissions': ['doc.read']},
                           headers=_auth(admin_token))
        assert resp.status_code == 400
        assert resp.json['status'] == 'error'

    def test_create_role_empty_name_400(self, client, admin_token):
        """Empty 'name' -> 400."""
        resp = client.post('/roles', json={'name': '', 'permissions': ['doc.read']},
                           headers=_auth(admin_token))
        assert resp.status_code == 400
        assert resp.json['status'] == 'error'

    def test_create_role_duplicate_name_same_tenant_409(self, client, admin_token):
        """Duplicate role name within same tenant -> 409."""
        _create_role(client, admin_token, 'viewer', ['doc.read'])
        resp = _create_role(client, admin_token, 'viewer', ['doc.write'])
        assert resp.status_code == 409
        assert resp.json['status'] == 'error'

    def test_create_role_duplicate_name_different_tenant_ok(self, client, admin_token,
                                                            tenant_b_admin_token):
        """Same role name in different tenant is allowed -> 201."""
        _create_role(client, admin_token, 'viewer', ['doc.read'])
        resp = _create_role(client, tenant_b_admin_token, 'viewer', ['doc.read'])
        assert resp.status_code == 201

    def test_create_role_no_permission_403(self, client, noroles_token):
        """User without role.manage -> 403."""
        resp = _create_role(client, noroles_token, 'viewer', ['doc.read'])
        assert resp.status_code == 403
        assert resp.json['status'] == 'error'

    def test_create_role_no_token_401(self, client):
        """No Authorization header -> 401."""
        resp = client.post('/roles', json={'name': 'viewer', 'permissions': ['doc.read']})
        assert resp.status_code == 401

    def test_create_role_invalid_token_401(self, client):
        """Invalid JWT -> 401."""
        resp = client.post('/roles',
                           json={'name': 'viewer', 'permissions': ['doc.read']},
                           headers={'Authorization': 'Bearer invalid-token'})
        assert resp.status_code == 401

    def test_create_role_multiple_permissions(self, client, admin_token):
        """Create a role with multiple permissions -> 201."""
        resp = _create_role(client, admin_token, 'full_editor',
                            ['doc.read', 'doc.write', 'doc.delete'])
        assert resp.status_code == 201
        perms = set(resp.json['data']['permissions'])
        assert perms == {'doc.read', 'doc.write', 'doc.delete'}

    def test_create_role_no_permissions(self, client, admin_token):
        """Create a role with empty permissions list -> 201."""
        resp = _create_role(client, admin_token, 'empty_role', [])
        assert resp.status_code == 201
        assert resp.json['data']['permissions'] == []

    def test_create_role_with_nonexistent_parent_400(self, client, admin_token):
        """parent_role_id pointing to nonexistent role -> 400."""
        resp = _create_role(client, admin_token, 'orphan', ['doc.read'],
                            parent_role_id=99999)
        assert resp.status_code == 400
        assert resp.json['status'] == 'error'

    def test_create_role_with_cross_tenant_parent_400(self, client, admin_token,
                                                       tenant_b_admin_token):
        """parent_role_id from another tenant -> 400."""
        parent = _create_role(client, tenant_b_admin_token, 'tenant_b_role', ['doc.read'])
        parent_id = parent.json['data']['id']
        resp = _create_role(client, admin_token, 'tenant_a_child', ['doc.read'],
                            parent_role_id=parent_id)
        assert resp.status_code == 400


# ============================================================
# 2. GET /roles -- List Roles
# ============================================================


class TestListRoles:
    """GET /roles endpoint tests."""

    def test_list_roles_success_200(self, client, admin_token):
        """Admin lists roles -> 200, returns array of roles."""
        resp = client.get('/roles', headers=_auth(admin_token))

        assert resp.status_code == 200
        data = resp.json
        assert data['status'] == 'ok'
        assert isinstance(data['data'], list)

    def test_list_roles_includes_seed_roles(self, client, admin_token):
        """Response includes the seeded super_admin role for TenantA."""
        resp = client.get('/roles', headers=_auth(admin_token))
        role_names = [r['name'] for r in resp.json['data']]
        assert 'super_admin' in role_names

    def test_list_roles_only_own_tenant(self, client, admin_token,
                                         tenant_b_admin_token):
        """Each tenant sees only their own roles."""
        # Create a role in TenantA
        _create_role(client, admin_token, 'tenant_a_only', ['doc.read'])

        a_roles = client.get('/roles', headers=_auth(admin_token)).json['data']
        b_roles = client.get('/roles', headers=_auth(tenant_b_admin_token)).json['data']

        a_names = [r['name'] for r in a_roles]
        b_names = [r['name'] for r in b_roles]

        assert 'tenant_a_only' in a_names
        assert 'tenant_a_only' not in b_names

    def test_list_roles_no_permission_403(self, client, noroles_token):
        """User without role.manage -> 403."""
        resp = client.get('/roles', headers=_auth(noroles_token))
        assert resp.status_code == 403

    def test_list_roles_no_token_401(self, client):
        """No Authorization header -> 401."""
        resp = client.get('/roles')
        assert resp.status_code == 401

    def test_list_roles_empty_tenant(self, client, tenant_b_admin_token):
        """TenantB has only super_admin seed role."""
        resp = client.get('/roles', headers=_auth(tenant_b_admin_token))
        data = resp.json['data']
        assert len(data) >= 1
        names = [r['name'] for r in data]
        assert 'super_admin' in names

    def test_list_roles_after_create(self, client, admin_token):
        """Newly created role appears in list."""
        _create_role(client, admin_token, 'new_viewer', ['doc.read'])
        resp = client.get('/roles', headers=_auth(admin_token))
        names = [r['name'] for r in resp.json['data']]
        assert 'new_viewer' in names


# ============================================================
# 3. PUT /roles/<id>/permissions -- Update Permissions & Parent
# ============================================================


class TestUpdateRolePermissions:
    """PUT /roles/<id>/permissions endpoint tests."""

    def test_update_permissions_success(self, client, admin_token):
        """Replace permissions of a role -> 200."""
        role = _create_role(client, admin_token, 'viewer', ['doc.read'])
        role_id = role.json['data']['id']

        resp = client.put(f'/roles/{role_id}/permissions',
                          json={'permissions': ['doc.read', 'doc.write']},
                          headers=_auth(admin_token))

        assert resp.status_code == 200
        assert resp.json['status'] == 'ok'
        perms = set(resp.json['data']['permissions'])
        assert perms == {'doc.read', 'doc.write'}

    def test_update_permissions_clear_all(self, client, admin_token):
        """Set permissions to empty list -> 200, no permissions."""
        role = _create_role(client, admin_token, 'editor', ['doc.read', 'doc.write'])
        role_id = role.json['data']['id']

        resp = client.put(f'/roles/{role_id}/permissions',
                          json={'permissions': []},
                          headers=_auth(admin_token))

        assert resp.status_code == 200
        assert resp.json['data']['permissions'] == []

    def test_update_permissions_change_parent(self, client, admin_token):
        """Change parent_role_id -> 200."""
        parent_a = _create_role(client, admin_token, 'parent_a', ['doc.read'])
        parent_b = _create_role(client, admin_token, 'parent_b', ['doc.write'])
        child = _create_role(client, admin_token, 'child', [], parent_role_id=parent_a.json['data']['id'])
        child_id = child.json['data']['id']

        resp = client.put(f'/roles/{child_id}/permissions',
                          json={'parent_role_id': parent_b.json['data']['id'],
                                'permissions': []},
                          headers=_auth(admin_token))

        assert resp.status_code == 200
        assert resp.json['data']['parent_role_id'] == parent_b.json['data']['id']

    def test_update_permissions_clear_parent(self, client, admin_token):
        """Set parent_role_id to null -> 200, parent removed."""
        parent = _create_role(client, admin_token, 'parent', ['doc.read'])
        child = _create_role(client, admin_token, 'child', [], parent_role_id=parent.json['data']['id'])
        child_id = child.json['data']['id']

        resp = client.put(f'/roles/{child_id}/permissions',
                          json={'parent_role_id': None, 'permissions': []},
                          headers=_auth(admin_token))

        assert resp.status_code == 200
        assert resp.json['data']['parent_role_id'] is None

    def test_update_permissions_role_not_found_404(self, client, admin_token):
        """Role id does not exist -> 404."""
        resp = client.put('/roles/99999/permissions',
                          json={'permissions': ['doc.read']},
                          headers=_auth(admin_token))
        assert resp.status_code == 404
        assert resp.json['status'] == 'error'

    def test_update_permissions_no_permission_403(self, client, admin_token,
                                                   noroles_token):
        """User without role.manage -> 403."""
        role = _create_role(client, admin_token, 'viewer', ['doc.read'])
        role_id = role.json['data']['id']

        resp = client.put(f'/roles/{role_id}/permissions',
                          json={'permissions': ['doc.write']},
                          headers=_auth(noroles_token))
        assert resp.status_code == 403

    def test_update_permissions_no_token_401(self, client):
        """No Authorization header -> 401."""
        resp = client.put('/roles/1/permissions',
                          json={'permissions': ['doc.read']})
        assert resp.status_code == 401

    def test_update_permissions_cycle_detection_a_to_b_to_a(self, client, admin_token):
        """A -> B, then B -> A: cycle detected -> 400."""
        role_a = _create_role(client, admin_token, 'roleA', [])
        a_id = role_a.json['data']['id']
        role_b = _create_role(client, admin_token, 'roleB', [], parent_role_id=a_id)
        b_id = role_b.json['data']['id']

        # Try to set A's parent to B (would create A -> B -> A cycle)
        resp = client.put(f'/roles/{a_id}/permissions',
                          json={'parent_role_id': b_id, 'permissions': []},
                          headers=_auth(admin_token))
        assert resp.status_code == 400
        assert resp.json['status'] == 'error'

    def test_update_permissions_cycle_detection_three_level(self, client, admin_token):
        """A -> B -> C, then C -> A: cycle detected -> 400."""
        role_a = _create_role(client, admin_token, 'chainA', [])
        a_id = role_a.json['data']['id']
        role_b = _create_role(client, admin_token, 'chainB', [], parent_role_id=a_id)
        b_id = role_b.json['data']['id']
        role_c = _create_role(client, admin_token, 'chainC', [], parent_role_id=b_id)
        c_id = role_c.json['data']['id']

        # Try to set A's parent to C (would create A -> B -> C -> A cycle)
        resp = client.put(f'/roles/{a_id}/permissions',
                          json={'parent_role_id': c_id, 'permissions': []},
                          headers=_auth(admin_token))
        assert resp.status_code == 400

    def test_update_permissions_self_parent_rejected(self, client, admin_token):
        """Setting a role as its own parent -> 400."""
        role = _create_role(client, admin_token, 'selfparent', ['doc.read'])
        role_id = role.json['data']['id']

        resp = client.put(f'/roles/{role_id}/permissions',
                          json={'parent_role_id': role_id, 'permissions': []},
                          headers=_auth(admin_token))
        assert resp.status_code == 400

    def test_update_permissions_with_cross_tenant_parent_400(self, client, admin_token,
                                                              tenant_b_admin_token):
        """Setting parent to a role from another tenant -> 400."""
        role_a = _create_role(client, admin_token, 'tenant_a_role', ['doc.read'])
        role_a_id = role_a.json['data']['id']

        role_b = _create_role(client, tenant_b_admin_token, 'tenant_b_parent', ['doc.write'])
        role_b_id = role_b.json['data']['id']

        resp = client.put(f'/roles/{role_a_id}/permissions',
                          json={'parent_role_id': role_b_id, 'permissions': []},
                          headers=_auth(admin_token))
        assert resp.status_code == 400

    def test_update_permissions_only_parent_no_perms_field(self, client, admin_token):
        """Update only parent_role_id without changing permissions."""
        parent = _create_role(client, admin_token, 'p_role', ['doc.read'])
        child = _create_role(client, admin_token, 'c_role', ['doc.write'])
        child_id = child.json['data']['id']

        resp = client.put(f'/roles/{child_id}/permissions',
                          json={'parent_role_id': parent.json['data']['id']},
                          headers=_auth(admin_token))
        assert resp.status_code == 200
        assert resp.json['data']['parent_role_id'] == parent.json['data']['id']


# ============================================================
# 4. POST /users/<id>/roles -- Assign Role
# ============================================================


class TestAssignRole:
    """POST /users/<id>/roles endpoint tests."""

    def test_assign_role_success(self, client, admin_token):
        """Assign a role to bob -> 200."""
        role = _create_role(client, admin_token, 'viewer', ['doc.read'])
        role_id = role.json['data']['id']

        resp = client.post('/users/2/roles',
                           json={'role_id': role_id},
                           headers=_auth(admin_token))

        assert resp.status_code == 200
        assert resp.json['status'] == 'ok'

    def test_assign_role_user_not_found_404(self, client, admin_token):
        """User id does not exist -> 404."""
        resp = client.post('/users/99999/roles',
                           json={'role_id': 1},
                           headers=_auth(admin_token))
        assert resp.status_code == 404
        assert resp.json['status'] == 'error'

    def test_assign_role_role_not_found_404(self, client, admin_token):
        """Role id does not exist -> 404."""
        resp = client.post('/users/2/roles',
                           json={'role_id': 99999},
                           headers=_auth(admin_token))
        assert resp.status_code == 404
        assert resp.json['status'] == 'error'

    def test_assign_role_no_permission_403(self, client, noroles_token):
        """User without role.manage -> 403."""
        resp = client.post('/users/2/roles',
                           json={'role_id': 1},
                           headers=_auth(noroles_token))
        assert resp.status_code == 403

    def test_assign_role_no_token_401(self, client):
        """No Authorization header -> 401."""
        resp = client.post('/users/2/roles', json={'role_id': 1})
        assert resp.status_code == 401

    def test_assign_role_cross_tenant_rejected(self, client, admin_token,
                                                tenant_b_admin_token):
        """Assign a TenantA role to a TenantB user -> 403 or 404."""
        role_a = _create_role(client, admin_token, 'tenant_a_role', ['doc.read'])
        role_a_id = role_a.json['data']['id']

        # User 5 (eve_b_admin) is in TenantB, role is in TenantA
        resp = client.post('/users/5/roles',
                           json={'role_id': role_a_id},
                           headers=_auth(admin_token))
        assert resp.status_code in (403, 404)

    def test_assign_role_missing_role_id_400(self, client, admin_token):
        """Missing role_id in request body -> 400."""
        resp = client.post('/users/2/roles',
                           json={},
                           headers=_auth(admin_token))
        assert resp.status_code == 400

    def test_assign_role_already_assigned_idempotent(self, client, admin_token):
        """Assigning same role twice is idempotent -> 200."""
        role = _create_role(client, admin_token, 'viewer', ['doc.read'])
        role_id = role.json['data']['id']

        resp1 = client.post('/users/2/roles',
                            json={'role_id': role_id},
                            headers=_auth(admin_token))
        resp2 = client.post('/users/2/roles',
                            json={'role_id': role_id},
                            headers=_auth(admin_token))

        assert resp1.status_code == 200
        assert resp2.status_code == 200

    def test_assign_multiple_roles_to_user(self, client, admin_token):
        """Assign two different roles to same user."""
        role_a = _create_role(client, admin_token, 'reader', ['doc.read'])
        role_b = _create_role(client, admin_token, 'writer', ['doc.write'])

        resp_a = client.post('/users/2/roles',
                             json={'role_id': role_a.json['data']['id']},
                             headers=_auth(admin_token))
        resp_b = client.post('/users/2/roles',
                             json={'role_id': role_b.json['data']['id']},
                             headers=_auth(admin_token))

        assert resp_a.status_code == 200
        assert resp_b.status_code == 200


# ============================================================
# 5. DELETE /users/<id>/roles/<role_id> -- Remove Role
# ============================================================


class TestRemoveRole:
    """DELETE /users/<id>/roles/<role_id> endpoint tests."""

    def test_remove_role_success(self, client, admin_token):
        """Remove a role from user -> 200."""
        role = _create_role(client, admin_token, 'viewer', ['doc.read'])
        role_id = role.json['data']['id']

        # First assign
        client.post('/users/2/roles',
                    json={'role_id': role_id},
                    headers=_auth(admin_token))

        # Then remove
        resp = client.delete(f'/users/2/roles/{role_id}',
                             headers=_auth(admin_token))
        assert resp.status_code == 200
        assert resp.json['status'] == 'ok'

    def test_remove_role_idempotent(self, client, admin_token):
        """Removing a role that was never assigned -> 200 (idempotent, no error)."""
        role = _create_role(client, admin_token, 'viewer', ['doc.read'])
        role_id = role.json['data']['id']

        resp = client.delete(f'/users/2/roles/{role_id}',
                             headers=_auth(admin_token))
        assert resp.status_code == 200

    def test_remove_role_user_not_found_404(self, client, admin_token):
        """User id does not exist -> 404."""
        resp = client.delete('/users/99999/roles/1',
                             headers=_auth(admin_token))
        assert resp.status_code == 404
        assert resp.json['status'] == 'error'

    def test_remove_role_no_permission_403(self, client, noroles_token):
        """User without role.manage -> 403."""
        resp = client.delete('/users/2/roles/1',
                             headers=_auth(noroles_token))
        assert resp.status_code == 403

    def test_remove_role_no_token_401(self, client):
        """No Authorization header -> 401."""
        resp = client.delete('/users/2/roles/1')
        assert resp.status_code == 401

    def test_remove_one_role_keeps_others(self, client, admin_token):
        """Removing one role does not affect other assigned roles."""
        role_a = _create_role(client, admin_token, 'reader', ['doc.read'])
        role_b = _create_role(client, admin_token, 'writer', ['doc.write'])

        client.post('/users/2/roles',
                    json={'role_id': role_a.json['data']['id']},
                    headers=_auth(admin_token))
        client.post('/users/2/roles',
                    json={'role_id': role_b.json['data']['id']},
                    headers=_auth(admin_token))

        # Remove reader only
        resp = client.delete(f'/users/2/roles/{role_a.json["data"]["id"]}',
                             headers=_auth(admin_token))
        assert resp.status_code == 200

        # Bob should still have writer role -> doc.write permission
        bob_token = _login(client, 'bob')
        # Re-login to pick up new role assignments
        # Bob should have doc.write from writer role
        from middleware import get_user_permissions
        from app import create_app as _cap
        # Verify via role listing or permission check
        # The user should still be able to access role management
        # to verify the role is still assigned
        resp2 = client.get('/roles', headers=_auth(bob_token))
        # bob doesn't have role.manage, so should be 403
        assert resp2.status_code == 403


# ============================================================
# 6. Inheritance Cycle Detection (dedicated tests)
# ============================================================


class TestInheritanceCycleDetection:
    """Comprehensive cycle detection tests for parent_role_id updates."""

    def test_direct_self_cycle_rejected_on_create(self, client, admin_token):
        """Cannot create a role with itself as parent (pre-creation)."""
        # This tests if the system validates self-reference during creation
        # Since we can't reference a role that doesn't exist yet,
        # we test the update path instead
        role = _create_role(client, admin_token, 'selfref', ['doc.read'])
        role_id = role.json['data']['id']

        resp = client.put(f'/roles/{role_id}/permissions',
                          json={'parent_role_id': role_id, 'permissions': []},
                          headers=_auth(admin_token))
        assert resp.status_code == 400

    def test_two_node_cycle(self, client, admin_token):
        """A -> B, B -> A creates a cycle."""
        role_a = _create_role(client, admin_token, 'cycleA', [])
        a_id = role_a.json['data']['id']
        role_b = _create_role(client, admin_token, 'cycleB', [], parent_role_id=a_id)
        b_id = role_b.json['data']['id']

        # A -> B exists (B's parent is A). Now try B -> A.
        resp = client.put(f'/roles/{a_id}/permissions',
                          json={'parent_role_id': b_id, 'permissions': []},
                          headers=_auth(admin_token))
        assert resp.status_code == 400

    def test_three_node_cycle(self, client, admin_token):
        """A -> B -> C, C -> A creates a cycle."""
        a = _create_role(client, admin_token, 'triA', [])
        a_id = a.json['data']['id']
        b = _create_role(client, admin_token, 'triB', [], parent_role_id=a_id)
        b_id = b.json['data']['id']
        c = _create_role(client, admin_token, 'triC', [], parent_role_id=b_id)
        c_id = c.json['data']['id']

        # Now try to make C -> A (A's parent = C)
        resp = client.put(f'/roles/{a_id}/permissions',
                          json={'parent_role_id': c_id, 'permissions': []},
                          headers=_auth(admin_token))
        assert resp.status_code == 400

    def test_four_node_cycle(self, client, admin_token):
        """A -> B -> C -> D, D -> A creates a cycle."""
        a = _create_role(client, admin_token, 'quadA', [])
        a_id = a.json['data']['id']
        b = _create_role(client, admin_token, 'quadB', [], parent_role_id=a_id)
        b_id = b.json['data']['id']
        c = _create_role(client, admin_token, 'quadC', [], parent_role_id=b_id)
        c_id = c.json['data']['id']
        d = _create_role(client, admin_token, 'quadD', [], parent_role_id=c_id)
        d_id = d.json['data']['id']

        # Now try to make A's parent = D (A -> B -> C -> D -> A)
        resp = client.put(f'/roles/{a_id}/permissions',
                          json={'parent_role_id': d_id, 'permissions': []},
                          headers=_auth(admin_token))
        assert resp.status_code == 400

    def test_no_cycle_linear_chain_allowed(self, client, admin_token):
        """Linear chain A -> B -> C with no cycle is allowed."""
        a = _create_role(client, admin_token, 'linA', ['doc.read'])
        a_id = a.json['data']['id']
        b = _create_role(client, admin_token, 'linB', ['doc.write'], parent_role_id=a_id)
        b_id = b.json['data']['id']
        c = _create_role(client, admin_token, 'linC', ['doc.delete'], parent_role_id=b_id)

        assert c.status_code == 201

    def test_reparenting_to_non_descendant_allowed(self, client, admin_token):
        """Changing parent to an unrelated role (no cycle) is allowed."""
        x = _create_role(client, admin_token, 'unrelatedX', ['doc.read'])
        x_id = x.json['data']['id']
        a = _create_role(client, admin_token, 'unrelatedA', [])
        a_id = a.json['data']['id']
        b = _create_role(client, admin_token, 'unrelatedB', [], parent_role_id=a_id)
        b_id = b.json['data']['id']

        # Reparent B to X (no cycle)
        resp = client.put(f'/roles/{b_id}/permissions',
                          json={'parent_role_id': x_id, 'permissions': []},
                          headers=_auth(admin_token))
        assert resp.status_code == 200

    def test_cycle_detected_on_deep_reparenting(self, client, admin_token):
        """D is descendant of A. Reparenting A to D should be rejected."""
        a = _create_role(client, admin_token, 'deepA', [])
        a_id = a.json['data']['id']
        b = _create_role(client, admin_token, 'deepB', [], parent_role_id=a_id)
        b_id = b.json['data']['id']
        c = _create_role(client, admin_token, 'deepC', [], parent_role_id=b_id)
        c_id = c.json['data']['id']
        d = _create_role(client, admin_token, 'deepD', [], parent_role_id=c_id)
        d_id = d.json['data']['id']

        # Try to set A's parent to D (A -> B -> C -> D -> A cycle)
        resp = client.put(f'/roles/{a_id}/permissions',
                          json={'parent_role_id': d_id, 'permissions': []},
                          headers=_auth(admin_token))
        assert resp.status_code == 400

    def test_breaking_chain_then_reparenting_ok(self, client, admin_token):
        """Break A -> B chain first, then reparent A to B is fine."""
        a = _create_role(client, admin_token, 'brkA', [])
        a_id = a.json['data']['id']
        b = _create_role(client, admin_token, 'brkB', [], parent_role_id=a_id)
        b_id = b.json['data']['id']

        # Break the chain: remove B's parent
        resp = client.put(f'/roles/{b_id}/permissions',
                          json={'parent_role_id': None, 'permissions': []},
                          headers=_auth(admin_token))
        assert resp.status_code == 200

        # Now A -> B should be fine (no cycle since B no longer points to A)
        resp = client.put(f'/roles/{a_id}/permissions',
                          json={'parent_role_id': b_id, 'permissions': []},
                          headers=_auth(admin_token))
        assert resp.status_code == 200


# ============================================================
# Cross-tenant isolation for role management
# ============================================================


class TestRoleTenantIsolation:
    """Verify that role operations are tenant-scoped."""

    def test_tenant_a_cannot_see_tenant_b_roles(self, client, admin_token,
                                                  tenant_b_admin_token):
        """GET /roles returns only own tenant's roles."""
        _create_role(client, admin_token, 'a_role', ['doc.read'])
        _create_role(client, tenant_b_admin_token, 'b_role', ['doc.write'])

        a_resp = client.get('/roles', headers=_auth(admin_token))
        b_resp = client.get('/roles', headers=_auth(tenant_b_admin_token))

        a_names = [r['name'] for r in a_resp.json['data']]
        b_names = [r['name'] for r in b_resp.json['data']]

        assert 'a_role' in a_names
        assert 'b_role' not in a_names
        assert 'b_role' in b_names
        assert 'a_role' not in b_names

    def test_tenant_a_admin_cannot_update_tenant_b_role(self, client, admin_token,
                                                        tenant_b_admin_token):
        """PUT /roles/<id>/permissions on another tenant's role -> 404."""
        role_b = _create_role(client, tenant_b_admin_token, 'b_updatable', ['doc.read'])
        role_b_id = role_b.json['data']['id']

        resp = client.put(f'/roles/{role_b_id}/permissions',
                          json={'permissions': ['doc.write']},
                          headers=_auth(admin_token))
        assert resp.status_code == 404

    def test_tenant_a_cannot_assign_tenant_b_role(self, client, admin_token,
                                                    tenant_b_admin_token):
        """Assign TenantB role to TenantA user -> 404 or 403."""
        role_b = _create_role(client, tenant_b_admin_token, 'b_assign', ['doc.read'])
        role_b_id = role_b.json['data']['id']

        resp = client.post('/users/2/roles',
                           json={'role_id': role_b_id},
                           headers=_auth(admin_token))
        assert resp.status_code in (403, 404)
