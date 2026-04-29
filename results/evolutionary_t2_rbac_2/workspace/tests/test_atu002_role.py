"""
ATU-002 -- Role Management Routes Unit Tests

Coverage:
- POST /roles: create role (201), duplicate name (409), parent validation, permission check
- GET /roles: list roles scoped to current tenant
- PUT /roles/<id>/permissions: update permissions + parent, cycle detection
- POST /users/<id>/roles: assign role to user
- DELETE /users/<id>/roles/<role_id>: remove role from user (idempotent)
- Cross-tenant isolation for role assignment
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
    """Create test client with seed data (two tenants, admin users, permissions)."""
    app = create_app()
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    app.config['JWT_SECRET'] = 'test-secret'

    with app.test_client() as c:
        with app.app_context():
            db.drop_all()
            db.create_all()

            # --- Tenants ---
            db.session.add(Tenant(id=1, name='TenantA'))
            db.session.add(Tenant(id=2, name='TenantB'))

            # --- Users (password = 'pw') ---
            pw = hash_password('pw')
            db.session.add(User(id=1, tenant_id=1, username='alice_admin', password_hash=pw))
            db.session.add(User(id=2, tenant_id=1, username='bob_editor', password_hash=pw))
            db.session.add(User(id=3, tenant_id=1, username='carol_viewer', password_hash=pw))
            db.session.add(User(id=4, tenant_id=1, username='dave_noroles', password_hash=pw))
            db.session.add(User(id=5, tenant_id=2, username='eve_b_admin', password_hash=pw))
            db.session.add(User(id=6, tenant_id=2, username='frank_b_user', password_hash=pw))

            # --- Permissions ---
            perm_codes = [
                'doc.read', 'doc.write', 'doc.write.any', 'doc.delete', 'role.manage',
            ]
            for code in perm_codes:
                db.session.add(Permission(code=code))
            db.session.flush()

            # --- Admin roles (one per tenant, with all permissions) ---
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

            # Assign admin roles to users
            db.session.execute(user_roles.insert().values(user_id=1, role_id=1))
            db.session.execute(user_roles.insert().values(user_id=5, role_id=2))

            db.session.commit()
        yield c


# ============================================================
# Helpers
# ============================================================


def _login(client, username):
    """Login and return JWT token."""
    resp = client.post('/login', json={'username': username, 'password': 'pw'})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    return resp.json['data']['token']


def _auth_headers(token):
    """Build Authorization header dict."""
    return {'Authorization': f'Bearer {token}'}


def _create_role(client, admin_token, name, permissions, parent_role_id=None):
    """POST /roles helper."""
    body = {'name': name, 'permissions': permissions}
    if parent_role_id is not None:
        body['parent_role_id'] = parent_role_id
    return client.post('/roles', json=body, headers=_auth_headers(admin_token))


@pytest.fixture
def admin_token(client):
    """Tenant A admin token (alice_admin, has role.manage)."""
    return _login(client, 'alice_admin')


@pytest.fixture
def tenant_b_admin_token(client):
    """Tenant B admin token (eve_b_admin, has role.manage)."""
    return _login(client, 'eve_b_admin')


@pytest.fixture
def noroles_token(client):
    """Tenant A user with no roles (dave_noroles)."""
    return _login(client, 'dave_noroles')


# ============================================================
# POST /roles -- Create Role
# ============================================================


class TestCreateRole:
    """ATU-002 POST /roles -- Create a new role."""

    def test_create_role_returns_201(self, client, admin_token):
        """Successfully create a role returns 201 with id, name, permissions."""
        resp = _create_role(client, admin_token, 'viewer', ['doc.read'])
        assert resp.status_code == 201
        data = resp.json['data']
        assert 'id' in data
        assert data['name'] == 'viewer'
        assert 'doc.read' in data['permissions']

    def test_create_role_response_has_expected_fields(self, client, admin_token):
        """Response data must include id, name, parent_role_id, permissions."""
        resp = _create_role(client, admin_token, 'editor', ['doc.read', 'doc.write'])
        assert resp.status_code == 201
        data = resp.json['data']
        assert 'id' in data
        assert isinstance(data['id'], int)
        assert data['name'] == 'editor'
        assert data['parent_role_id'] is None
        assert isinstance(data['permissions'], list)
        assert set(data['permissions']) == {'doc.read', 'doc.write'}

    def test_create_role_with_parent(self, client, admin_token):
        """Create a child role referencing a parent_role_id."""
        parent = _create_role(client, admin_token, 'base_role', ['doc.read'])
        parent_id = parent.json['data']['id']

        resp = _create_role(
            client, admin_token, 'child_role', ['doc.write'], parent_role_id=parent_id,
        )
        assert resp.status_code == 201
        data = resp.json['data']
        assert data['parent_role_id'] == parent_id
        assert data['name'] == 'child_role'

    def test_no_permission_returns_403(self, client, noroles_token):
        """User without role.manage permission cannot create a role (403)."""
        resp = _create_role(client, noroles_token, 'viewer', ['doc.read'])
        assert resp.status_code == 403

    def test_duplicate_role_name_returns_409(self, client, admin_token):
        """Creating a role with the same name in the same tenant returns 409."""
        _create_role(client, admin_token, 'viewer', ['doc.read'])
        resp = _create_role(client, admin_token, 'viewer', ['doc.write'])
        assert resp.status_code == 409

    def test_duplicate_name_across_tenants_allowed(self, client, admin_token, tenant_b_admin_token):
        """Same role name is allowed in different tenants."""
        resp_a = _create_role(client, admin_token, 'viewer', ['doc.read'])
        assert resp_a.status_code == 201

        resp_b = _create_role(client, tenant_b_admin_token, 'viewer', ['doc.read'])
        assert resp_b.status_code == 201

    def test_missing_name_returns_400(self, client, admin_token):
        """Request body without 'name' field returns 400."""
        resp = client.post('/roles', json={'permissions': ['doc.read']},
                           headers=_auth_headers(admin_token))
        assert resp.status_code == 400

    def test_parent_not_found_returns_400(self, client, admin_token):
        """parent_role_id referencing a non-existent role returns 400."""
        resp = _create_role(
            client, admin_token, 'orphan', ['doc.read'], parent_role_id=99999,
        )
        assert resp.status_code == 400

    def test_parent_cross_tenant_returns_400(self, client, admin_token, tenant_b_admin_token):
        """parent_role_id from a different tenant returns 400."""
        # Create a role in Tenant B
        b_role = _create_role(client, tenant_b_admin_token, 'b_only_role', ['doc.read'])
        b_role_id = b_role.json['data']['id']

        # Tenant A admin tries to use it as parent
        resp = _create_role(
            client, admin_token, 'a_role_with_b_parent', ['doc.read'],
            parent_role_id=b_role_id,
        )
        assert resp.status_code == 400


# ============================================================
# GET /roles -- List Roles
# ============================================================


class TestListRoles:
    """ATU-002 GET /roles -- List roles for the current tenant."""

    def test_list_roles_returns_200(self, client, admin_token):
        """List roles returns 200 with a list of roles."""
        resp = client.get('/roles', headers=_auth_headers(admin_token))
        assert resp.status_code == 200
        assert isinstance(resp.json['data'], list)

    def test_list_roles_scoped_to_tenant(self, client, admin_token, tenant_b_admin_token):
        """Each tenant only sees its own roles."""
        # Create roles in Tenant A
        _create_role(client, admin_token, 'a_role1', ['doc.read'])
        _create_role(client, admin_token, 'a_role2', ['doc.write'])

        # Create a role in Tenant B
        _create_role(client, tenant_b_admin_token, 'b_role1', ['doc.read'])

        # Tenant A sees only Tenant A roles (including super_admin)
        a_roles = client.get('/roles', headers=_auth_headers(admin_token)).json['data']
        a_names = [r['name'] for r in a_roles]
        assert 'a_role1' in a_names
        assert 'a_role2' in a_names
        assert 'b_role1' not in a_names

        # Tenant B sees only Tenant B roles (including super_admin)
        b_roles = client.get('/roles', headers=_auth_headers(tenant_b_admin_token)).json['data']
        b_names = [r['name'] for r in b_roles]
        assert 'b_role1' in b_names
        assert 'a_role1' not in b_names

    def test_list_roles_contains_expected_fields(self, client, admin_token):
        """Each role in the list must have id, name, tenant_id, parent_role_id, permissions."""
        _create_role(client, admin_token, 'fieldcheck', ['doc.read'])
        resp = client.get('/roles', headers=_auth_headers(admin_token))
        role = next(r for r in resp.json['data'] if r['name'] == 'fieldcheck')
        assert 'id' in role
        assert 'name' in role
        assert 'tenant_id' in role
        assert 'parent_role_id' in role
        assert 'permissions' in role

    def test_no_permission_returns_403(self, client, noroles_token):
        """User without role.manage cannot list roles (403)."""
        resp = client.get('/roles', headers=_auth_headers(noroles_token))
        assert resp.status_code == 403


# ============================================================
# PUT /roles/<id>/permissions -- Update Permissions & Parent
# ============================================================


class TestUpdateRolePermissions:
    """ATU-002 PUT /roles/<id>/permissions -- Update role's permission set and parent."""

    def test_update_permissions_returns_200(self, client, admin_token):
        """Replace the permission set of a role returns 200."""
        role = _create_role(client, admin_token, 'updatable', ['doc.read'])
        role_id = role.json['data']['id']

        resp = client.put(
            f'/roles/{role_id}/permissions',
            json={'permissions': ['doc.read', 'doc.write', 'doc.delete']},
            headers=_auth_headers(admin_token),
        )
        assert resp.status_code == 200
        data = resp.json['data']
        assert set(data['permissions']) == {'doc.read', 'doc.write', 'doc.delete'}

    def test_update_parent_role(self, client, admin_token):
        """Update a role's parent_role_id returns 200."""
        parent = _create_role(client, admin_token, 'new_parent', ['doc.read'])
        child = _create_role(client, admin_token, 'child', ['doc.write'])
        parent_id = parent.json['data']['id']
        child_id = child.json['data']['id']

        resp = client.put(
            f'/roles/{child_id}/permissions',
            json={'permissions': ['doc.write'], 'parent_role_id': parent_id},
            headers=_auth_headers(admin_token),
        )
        assert resp.status_code == 200
        assert resp.json['data']['parent_role_id'] == parent_id

    def test_cycle_detection_rejects_direct(self, client, admin_token):
        """Setting A as parent of B where B is already parent of A (cycle) returns 400."""
        a = _create_role(client, admin_token, 'roleA', [])
        b = _create_role(client, admin_token, 'roleB', [], parent_role_id=a.json['data']['id'])
        a_id = a.json['data']['id']
        b_id = b.json['data']['id']

        resp = client.put(
            f'/roles/{a_id}/permissions',
            json={'permissions': [], 'parent_role_id': b_id},
            headers=_auth_headers(admin_token),
        )
        assert resp.status_code == 400

    def test_cycle_detection_rejects_three_level(self, client, admin_token):
        """Detecting a cycle in a three-role chain returns 400."""
        a = _create_role(client, admin_token, 'cycleA', [])
        b = _create_role(client, admin_token, 'cycleB', [], parent_role_id=a.json['data']['id'])
        c = _create_role(client, admin_token, 'cycleC', [], parent_role_id=b.json['data']['id'])
        a_id = a.json['data']['id']
        c_id = c.json['data']['id']

        # Making A a child of C would create A -> B -> C -> A cycle
        resp = client.put(
            f'/roles/{a_id}/permissions',
            json={'permissions': [], 'parent_role_id': c_id},
            headers=_auth_headers(admin_token),
        )
        assert resp.status_code == 400

    def test_role_not_found_returns_404(self, client, admin_token):
        """Updating a non-existent role returns 404."""
        resp = client.put(
            '/roles/99999/permissions',
            json={'permissions': ['doc.read']},
            headers=_auth_headers(admin_token),
        )
        assert resp.status_code == 404

    def test_no_permission_returns_403(self, client, noroles_token):
        """User without role.manage cannot update permissions (403)."""
        resp = client.put(
            '/roles/1/permissions',
            json={'permissions': ['doc.read']},
            headers=_auth_headers(noroles_token),
        )
        assert resp.status_code == 403


# ============================================================
# POST /users/<id>/roles -- Assign Role to User
# ============================================================


class TestAssignRole:
    """ATU-002 POST /users/<id>/roles -- Assign a role to a user."""

    def test_assign_role_returns_200(self, client, admin_token):
        """Assign a role to a user in the same tenant returns 200."""
        role = _create_role(client, admin_token, 'assignable', ['doc.read'])
        role_id = role.json['data']['id']

        resp = client.post(
            '/users/2/roles',
            json={'role_id': role_id},
            headers=_auth_headers(admin_token),
        )
        assert resp.status_code == 200

    def test_assign_role_user_not_found_returns_404(self, client, admin_token):
        """Assigning a role to a non-existent user returns 404."""
        role = _create_role(client, admin_token, 'orphan_target', ['doc.read'])
        role_id = role.json['data']['id']

        resp = client.post(
            '/users/99999/roles',
            json={'role_id': role_id},
            headers=_auth_headers(admin_token),
        )
        assert resp.status_code == 404

    def test_assign_role_role_not_found_returns_404(self, client, admin_token):
        """Assigning a non-existent role returns 404."""
        resp = client.post(
            '/users/2/roles',
            json={'role_id': 99999},
            headers=_auth_headers(admin_token),
        )
        assert resp.status_code == 404

    def test_cross_tenant_assign_returns_403_or_404(self, client, admin_token, tenant_b_admin_token):
        """Assigning a Tenant A role to a Tenant B user returns 403 or 404."""
        a_role = _create_role(client, admin_token, 'a_only', ['doc.read'])
        a_role_id = a_role.json['data']['id']

        # User 6 is in Tenant B; role is in Tenant A
        resp = client.post(
            '/users/6/roles',
            json={'role_id': a_role_id},
            headers=_auth_headers(admin_token),
        )
        assert resp.status_code in (403, 404)

    def test_no_permission_returns_403(self, client, noroles_token):
        """User without role.manage cannot assign roles (403)."""
        resp = client.post(
            '/users/2/roles',
            json={'role_id': 1},
            headers=_auth_headers(noroles_token),
        )
        assert resp.status_code == 403


# ============================================================
# DELETE /users/<id>/roles/<role_id> -- Remove Role from User
# ============================================================


class TestRemoveRole:
    """ATU-002 DELETE /users/<id>/roles/<role_id> -- Remove role from user."""

    def test_remove_role_returns_200(self, client, admin_token):
        """Remove an assigned role from a user returns 200."""
        role = _create_role(client, admin_token, 'removable', ['doc.read'])
        role_id = role.json['data']['id']

        # Assign first
        client.post('/users/2/roles', json={'role_id': role_id},
                    headers=_auth_headers(admin_token))

        # Then remove
        resp = client.delete(
            f'/users/2/roles/{role_id}',
            headers=_auth_headers(admin_token),
        )
        assert resp.status_code == 200

    def test_idempotent_remove_returns_200(self, client, admin_token):
        """Removing a role that is not assigned to the user still returns 200 (idempotent)."""
        role = _create_role(client, admin_token, 'never_assigned', ['doc.read'])
        role_id = role.json['data']['id']

        # Role was never assigned to user 2
        resp = client.delete(
            f'/users/2/roles/{role_id}',
            headers=_auth_headers(admin_token),
        )
        assert resp.status_code == 200

    def test_remove_role_user_not_found_returns_404(self, client, admin_token):
        """Removing a role from a non-existent user returns 404."""
        resp = client.delete(
            '/users/99999/roles/1',
            headers=_auth_headers(admin_token),
        )
        assert resp.status_code == 404

    def test_no_permission_returns_403(self, client, noroles_token):
        """User without role.manage cannot remove roles (403)."""
        resp = client.delete(
            '/users/2/roles/1',
            headers=_auth_headers(noroles_token),
        )
        assert resp.status_code == 403
