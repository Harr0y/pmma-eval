"""
T2-3 RBAC 权限管理系统测试（多模块版本）

覆盖：认证、角色管理、文档 RBAC、多租户隔离、权限继承。
"""

import os
import sys
import tempfile
import datetime
import pytest
import jwt as pyjwt

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'starter'))

from app import create_app, db
from models import Tenant, User, Role, Permission, Document, user_roles, role_permissions
from middleware import hash_password


@pytest.fixture
def client():
    """创建测试客户端 + 种子数据（含 admin 角色）"""
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
            # Users
            pw = hash_password('pw')
            db.session.add(User(id=1, tenant_id=1, username='alice_admin', password_hash=pw))
            db.session.add(User(id=2, tenant_id=1, username='bob_editor', password_hash=pw))
            db.session.add(User(id=3, tenant_id=1, username='carol_viewer', password_hash=pw))
            db.session.add(User(id=4, tenant_id=1, username='dave_noroles', password_hash=pw))
            db.session.add(User(id=5, tenant_id=2, username='eve_b_admin', password_hash=pw))
            # Permissions
            perm_codes = ['doc.read', 'doc.write', 'doc.write.any', 'doc.delete', 'role.manage']
            for code in perm_codes:
                db.session.add(Permission(code=code))
            db.session.flush()
            # Admin roles
            db.session.add(Role(id=1, tenant_id=1, name='super_admin'))
            db.session.add(Role(id=2, tenant_id=2, name='super_admin'))
            db.session.flush()
            # Assign all permissions to admin roles via raw SQL
            db.session.execute(
                role_permissions.insert().from_select(['role_id', 'permission_id'],
                    db.session.query(db.literal(1), Permission.id)
                    .union_all(db.session.query(db.literal(2), Permission.id)))
            )
            # Assign admin roles to users via raw SQL
            db.session.execute(user_roles.insert().values(user_id=1, role_id=1))
            db.session.execute(user_roles.insert().values(user_id=5, role_id=2))
            db.session.commit()
        yield c


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
# 认证测试
# ============================================================

class TestAuth:
    def test_missing_token_returns_401(self, client):
        """无 token 访问受保护 API → 401"""
        resp = client.get('/documents')
        assert resp.status_code == 401

    def test_invalid_jwt_returns_401(self, client):
        """非法 JWT → 401"""
        resp = client.get('/documents', headers={'Authorization': 'Bearer not-a-jwt'})
        assert resp.status_code == 401

    def test_expired_jwt_returns_401(self, client):
        """过期 JWT → 401"""
        expired = pyjwt.encode(
            {'user_id': 1, 'tenant_id': 1,
             'exp': datetime.datetime.utcnow() - datetime.timedelta(hours=1)},
            'test-secret', algorithm='HS256'
        )
        resp = client.get('/documents', headers={'Authorization': f'Bearer {expired}'})
        assert resp.status_code == 401


# ============================================================
# 角色管理测试
# ============================================================

class TestRoleManagement:
    def test_admin_can_create_role(self, client, admin_token):
        resp = _create_role(client, admin_token, 'viewer', ['doc.read'])
        assert resp.status_code == 201
        assert resp.json['data']['name'] == 'viewer'

    def test_non_admin_cannot_create_role(self, client, noroles_token):
        resp = _create_role(client, noroles_token, 'viewer', ['doc.read'])
        assert resp.status_code == 403

    def test_role_inheritance_works(self, client, admin_token):
        """子角色继承父角色权限"""
        r_parent = _create_role(client, admin_token, 'viewer', ['doc.read'])
        assert r_parent.status_code == 201
        parent_id = r_parent.json['data']['id']

        r_child = _create_role(client, admin_token, 'editor', ['doc.write'],
                              parent_role_id=parent_id)
        assert r_child.status_code == 201

        # Assign child to bob
        client.post('/users/2/roles', json={'role_id': r_child.json['data']['id']},
                   headers=_auth(admin_token))

        bob_token = _login(client, 'bob_editor')
        read_resp = client.get('/documents', headers=_auth(bob_token))
        assert read_resp.status_code == 200  # inherits doc.read

    def test_inheritance_cycle_rejected(self, client, admin_token):
        """继承链环检测"""
        r_a = _create_role(client, admin_token, 'roleA', [])
        a_id = r_a.json['data']['id']
        r_b = _create_role(client, admin_token, 'roleB', [], parent_role_id=a_id)
        b_id = r_b.json['data']['id']

        resp = client.put(f'/roles/{a_id}/permissions',
                         json={'parent_role_id': b_id, 'permissions': []},
                         headers=_auth(admin_token))
        assert resp.status_code == 400


# ============================================================
# 文档 RBAC 测试
# ============================================================

class TestDocumentRBAC:
    def test_viewer_can_read(self, client, admin_token):
        _create_role(client, admin_token, 'viewer', ['doc.read'])
        roles = client.get('/roles', headers=_auth(admin_token)).json['data']
        viewer_id = next(r['id'] for r in roles if r['name'] == 'viewer')
        client.post('/users/3/roles', json={'role_id': viewer_id},
                   headers=_auth(admin_token))
        carol_token = _login(client, 'carol_viewer')
        assert client.get('/documents', headers=_auth(carol_token)).status_code == 200

    def test_viewer_cannot_post(self, client, admin_token):
        _create_role(client, admin_token, 'viewer', ['doc.read'])
        roles = client.get('/roles', headers=_auth(admin_token)).json['data']
        viewer_id = next(r['id'] for r in roles if r['name'] == 'viewer')
        client.post('/users/3/roles', json={'role_id': viewer_id},
                   headers=_auth(admin_token))
        carol_token = _login(client, 'carol_viewer')
        resp = client.post('/documents', json={'title': 'x', 'content': 'y'},
                          headers=_auth(carol_token))
        assert resp.status_code == 403

    def test_editor_can_edit_own(self, client, admin_token):
        _create_role(client, admin_token, 'editor', ['doc.read', 'doc.write'])
        roles = client.get('/roles', headers=_auth(admin_token)).json['data']
        editor_id = next(r['id'] for r in roles if r['name'] == 'editor')
        client.post('/users/2/roles', json={'role_id': editor_id},
                   headers=_auth(admin_token))
        bob_token = _login(client, 'bob_editor')
        c = client.post('/documents', json={'title': 't', 'content': 'c'},
                       headers=_auth(bob_token))
        assert c.status_code == 201
        doc_id = c.json['data']['id']
        u = client.put(f'/documents/{doc_id}', json={'title': 't2'},
                      headers=_auth(bob_token))
        assert u.status_code == 200

    def test_editor_cannot_edit_others(self, client, admin_token):
        _create_role(client, admin_token, 'editor', ['doc.read', 'doc.write'])
        roles = client.get('/roles', headers=_auth(admin_token)).json['data']
        editor_id = next(r['id'] for r in roles if r['name'] == 'editor')
        client.post('/users/2/roles', json={'role_id': editor_id},
                   headers=_auth(admin_token))
        c = client.post('/documents', json={'title': 'admin-doc', 'content': 'x'},
                       headers=_auth(admin_token))
        doc_id = c.json['data']['id']
        bob_token = _login(client, 'bob_editor')
        u = client.put(f'/documents/{doc_id}', json={'title': 'hacked'},
                      headers=_auth(bob_token))
        assert u.status_code == 403

    def test_admin_has_write_any(self, client, admin_token):
        _create_role(client, admin_token, 'editor', ['doc.read', 'doc.write'])
        roles = client.get('/roles', headers=_auth(admin_token)).json['data']
        editor_id = next(r['id'] for r in roles if r['name'] == 'editor')
        client.post('/users/2/roles', json={'role_id': editor_id},
                   headers=_auth(admin_token))
        bob_token = _login(client, 'bob_editor')
        c = client.post('/documents', json={'title': 'bob-doc', 'content': 'x'},
                       headers=_auth(bob_token))
        doc_id = c.json['data']['id']
        u = client.put(f'/documents/{doc_id}', json={'title': 'admin-edited'},
                      headers=_auth(admin_token))
        assert u.status_code == 200

    def test_no_read_permission_returns_403(self, client, noroles_token):
        resp = client.get('/documents', headers=_auth(noroles_token))
        assert resp.status_code == 403


# ============================================================
# 多租户测试
# ============================================================

class TestMultiTenant:
    def test_cross_tenant_document_returns_404(self, client, admin_token,
                                               tenant_b_admin_token):
        c = client.post('/documents', json={'title': 'a-only', 'content': 'x'},
                       headers=_auth(admin_token))
        doc_id = c.json['data']['id']
        resp = client.get(f'/documents/{doc_id}',
                         headers=_auth(tenant_b_admin_token))
        assert resp.status_code == 404

    def test_cross_tenant_role_forbidden(self, client, admin_token):
        r = _create_role(client, admin_token, 'viewer', ['doc.read'])
        vid = r.json['data']['id']
        # User 5 is tenant B, admin is tenant A
        resp = client.post('/users/5/roles', json={'role_id': vid},
                          headers=_auth(admin_token))
        assert resp.status_code in (403, 404)

    def test_list_documents_only_own_tenant(self, client, admin_token,
                                            tenant_b_admin_token):
        client.post('/documents', json={'title': 'a-doc', 'content': ''},
                   headers=_auth(admin_token))
        client.post('/documents', json={'title': 'b-doc', 'content': ''},
                   headers=_auth(tenant_b_admin_token))
        a_list = client.get('/documents', headers=_auth(admin_token)).json['data']
        b_list = client.get('/documents', headers=_auth(tenant_b_admin_token)).json['data']
        a_titles = [d['title'] for d in a_list]
        b_titles = [d['title'] for d in b_list]
        assert 'a-doc' in a_titles and 'b-doc' not in a_titles
        assert 'b-doc' in b_titles and 'a-doc' not in b_titles


# ============================================================
# 权限继承测试
# ============================================================

class TestPermissionInheritance:
    def test_add_permission_propagates(self, client, admin_token):
        """给父角色加权限 → 子角色自动拥有"""
        p = _create_role(client, admin_token, 'base', [])
        pid = p.json['data']['id']
        ch = _create_role(client, admin_token, 'baseplus', [], parent_role_id=pid)
        chid = ch.json['data']['id']
        client.post('/users/2/roles', json={'role_id': chid},
                   headers=_auth(admin_token))
        bob_token = _login(client, 'bob_editor')

        r1 = client.get('/documents', headers=_auth(bob_token))
        assert r1.status_code == 403

        # Add doc.read to parent
        client.put(f'/roles/{pid}/permissions',
                  json={'permissions': ['doc.read']},
                  headers=_auth(admin_token))

        r2 = client.get('/documents', headers=_auth(bob_token))
        assert r2.status_code == 200

    def test_remove_permission_revokes(self, client, admin_token):
        p = _create_role(client, admin_token, 'base2', ['doc.read'])
        pid = p.json['data']['id']
        ch = _create_role(client, admin_token, 'base2plus', [], parent_role_id=pid)
        chid = ch.json['data']['id']
        client.post('/users/2/roles', json={'role_id': chid},
                   headers=_auth(admin_token))
        bob_token = _login(client, 'bob_editor')
        assert client.get('/documents', headers=_auth(bob_token)).status_code == 200

        client.put(f'/roles/{pid}/permissions',
                  json={'permissions': []}, headers=_auth(admin_token))
        assert client.get('/documents', headers=_auth(bob_token)).status_code == 403

    def test_multi_role_union(self, client, admin_token):
        """用户拥有两个角色 → 权限取并集"""
        r1 = _create_role(client, admin_token, 'reader', ['doc.read'])
        r2 = _create_role(client, admin_token, 'writer', ['doc.write'])
        r1_id = r1.json['data']['id']
        r2_id = r2.json['data']['id']
        client.post('/users/2/roles', json={'role_id': r1_id},
                   headers=_auth(admin_token))
        client.post('/users/2/roles', json={'role_id': r2_id},
                   headers=_auth(admin_token))
        bob_token = _login(client, 'bob_editor')
        assert client.get('/documents', headers=_auth(bob_token)).status_code == 200
        assert client.post('/documents', json={'title': 't', 'content': 'c'},
                          headers=_auth(bob_token)).status_code == 201
