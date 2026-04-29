"""
T2-3 RBAC 系统隐藏评估测试（多模块版本）

这些测试对 Agent 不可见，用于最终评估。
覆盖：多模块集成一致性、跨模块安全边界、接口对齐。
"""

import os
import sys
import datetime
import pytest
import jwt as pyjwt

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'starter'))

from app import create_app, db
from models import Tenant, User, Role, Permission, Document, user_roles, role_permissions
from middleware import hash_password


@pytest.fixture
def client():
    app = create_app()
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    app.config['JWT_SECRET'] = 'test-secret'

    with app.test_client() as c:
        with app.app_context():
            db.drop_all()
            db.create_all()
            db.session.add(Tenant(id=1, name='TenantA'))
            db.session.add(Tenant(id=2, name='TenantB'))
            pw = hash_password('pw')
            db.session.add(User(id=1, tenant_id=1, username='alice_admin', password_hash=pw))
            db.session.add(User(id=2, tenant_id=1, username='bob_editor', password_hash=pw))
            db.session.add(User(id=3, tenant_id=1, username='carol_viewer', password_hash=pw))
            db.session.add(User(id=4, tenant_id=1, username='dave_noroles', password_hash=pw))
            db.session.add(User(id=5, tenant_id=2, username='eve_b_admin', password_hash=pw))
            perm_codes = ['doc.read', 'doc.write', 'doc.write.any', 'doc.delete', 'role.manage']
            for code in perm_codes:
                db.session.add(Permission(code=code))
            db.session.flush()
            db.session.add(Role(id=1, tenant_id=1, name='super_admin'))
            db.session.add(Role(id=2, tenant_id=2, name='super_admin'))
            db.session.flush()
            # Raw SQL for relationship assignments to avoid ORM GC issues
            db.session.execute(
                role_permissions.insert().from_select(['role_id', 'permission_id'],
                    db.session.query(db.literal(1), Permission.id)
                    .union_all(db.session.query(db.literal(2), Permission.id)))
            )
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
# 多模块集成测试
# ============================================================

class TestMultiModuleIntegration:
    def test_app_starts_successfully(self, client):
        """app.py 正常启动且路由注册正确"""
        assert client.get('/documents').status_code in (200, 401)
        assert client.post('/login', json={}).status_code in (200, 400)

    def test_models_importable(self, client):
        """models.py 的模型可正确导入"""
        with client.application.app_context():
            db.session.add(Permission(code='test.perm'))
            db.session.commit()
            assert Permission.query.filter_by(code='test.perm').first() is not None

    def test_three_blueprints_registered(self, client):
        """auth_bp, document_bp, role_bp 都正确注册"""
        assert client.post('/login', json={}).status_code == 400
        assert client.get('/documents').status_code == 401
        assert client.get('/roles').status_code == 401


# ============================================================
# 跨模块安全边界
# ============================================================

class TestCrossModuleSecurity:
    def test_tampered_jwt_returns_401(self, client):
        """篡改签名后的 JWT → 401（middleware 正确校验）"""
        token = _login(client, 'alice_admin')
        tampered = token[:-5] + 'XXXXX'
        resp = client.get('/documents', headers={'Authorization': f'Bearer {tampered}'})
        assert resp.status_code == 401

    def test_wrong_password_returns_401(self, client):
        """错误密码（routes_auth.py 与 models.py 一致）"""
        resp = client.post('/login', json={'username': 'alice_admin', 'password': 'wrong'})
        assert resp.status_code == 401

    def test_middleware_inheritance_matches_models(self, client, admin_token):
        """middleware.py 的继承遍历应正确使用 models.py 的 parent_role_id"""
        # Create 3-level chain
        gp = _create_role(client, admin_token, 'grandparent', ['doc.read'])
        gp_id = gp.json['data']['id']
        p = _create_role(client, admin_token, 'parent', ['doc.write'], parent_role_id=gp_id)
        p_id = p.json['data']['id']
        ch = _create_role(client, admin_token, 'child', [], parent_role_id=p_id)
        ch_id = ch.json['data']['id']

        client.post('/users/2/roles', json={'role_id': ch_id},
                   headers=_auth(admin_token))
        bob_token = _login(client, 'bob_editor')

        # bob should have doc.read (grandparent) and doc.write (parent)
        assert client.get('/documents', headers=_auth(bob_token)).status_code == 200
        assert client.post('/documents', json={'title': 'test', 'content': 'test'},
                          headers=_auth(bob_token)).status_code == 201

    def test_middleware_tenant_matches_models(self, client, admin_token, tenant_b_admin_token):
        """middleware.py 提取的 tenant_id 应与 models.py 的 tenant 边界一致"""
        c = client.post('/documents', json={'title': 'a-doc', 'content': 'secret'},
                       headers=_auth(admin_token))
        doc_id = c.json['data']['id']

        # tenant B admin should get 404
        resp = client.get(f'/documents/{doc_id}',
                         headers=_auth(tenant_b_admin_token))
        assert resp.status_code == 404

    def test_cross_tenant_update_blocked(self, client, admin_token, tenant_b_admin_token):
        """tenant B 不能修改 tenant A 的文档"""
        c = client.post('/documents', json={'title': 'a-doc', 'content': 'secret'},
                       headers=_auth(admin_token))
        doc_id = c.json['data']['id']

        resp = client.put(f'/documents/{doc_id}',
                         json={'title': 'hacked', 'content': 'pwned'},
                         headers=_auth(tenant_b_admin_token))
        assert resp.status_code == 404

    def test_cross_tenant_delete_blocked(self, client, admin_token, tenant_b_admin_token):
        """tenant B 不能删除 tenant A 的文档"""
        c = client.post('/documents', json={'title': 'a-doc', 'content': 'secret'},
                       headers=_auth(admin_token))
        doc_id = c.json['data']['id']

        resp = client.delete(f'/documents/{doc_id}',
                            headers=_auth(tenant_b_admin_token))
        assert resp.status_code == 404


# ============================================================
# 接口对齐测试
# ============================================================

class TestInterfaceAlignment:
    def test_permission_codes_consistent(self, client, admin_token):
        """routes_document.py 使用的权限码应与 models.py 的 Permission 一致"""
        # Admin with all perms should work
        assert client.get('/documents', headers=_auth(admin_token)).status_code == 200
        assert client.post('/documents', json={'title': 't', 'content': 'c'},
                          headers=_auth(admin_token)).status_code == 201

    def test_role_response_matches_model(self, client, admin_token):
        """角色路由返回的字段应与 models.py 一致"""
        r = _create_role(client, admin_token, 'test_role', ['doc.read'])
        data = r.json['data']
        assert 'id' in data
        assert 'name' in data
        assert 'parent_role_id' in data
        assert 'permissions' in data

    def test_document_response_matches_model(self, client, admin_token):
        """文档路由返回的字段应与 models.py 一致"""
        c = client.post('/documents', json={'title': 'test', 'content': 'body'},
                       headers=_auth(admin_token))
        data = c.json['data']
        assert 'id' in data
        assert 'tenant_id' in data
        assert 'owner_id' in data
        assert 'title' in data
        assert 'content' in data


# ============================================================
# 角色管理安全
# ============================================================

class TestRoleManagementEdgeCases:
    def test_duplicate_role_name_same_tenant(self, client, admin_token):
        r1 = _create_role(client, admin_token, 'viewer', ['doc.read'])
        assert r1.status_code == 201
        r2 = _create_role(client, admin_token, 'viewer', ['doc.read'])
        assert r2.status_code in (400, 409)

    def test_remove_user_role(self, client, admin_token):
        """移除用户角色后权限应消失"""
        r = _create_role(client, admin_token, 'reader', ['doc.read'])
        rid = r.json['data']['id']
        client.post('/users/4/roles', json={'role_id': rid},
                   headers=_auth(admin_token))
        dave_token = _login(client, 'dave_noroles')
        assert client.get('/documents', headers=_auth(dave_token)).status_code == 200

        client.delete(f'/users/4/roles/{rid}', headers=_auth(admin_token))
        dave_token = _login(client, 'dave_noroles')
        assert client.get('/documents', headers=_auth(dave_token)).status_code == 403

    def test_assign_nonexistent_role(self, client, admin_token):
        resp = client.post('/users/2/roles', json={'role_id': 99999},
                          headers=_auth(admin_token))
        assert resp.status_code in (400, 404)

    def test_cross_tenant_same_role_name(self, client, admin_token, tenant_b_admin_token):
        """不同 tenant 可以创建同名角色"""
        _create_role(client, admin_token, 'viewer', ['doc.read'])
        r = _create_role(client, tenant_b_admin_token, 'viewer', ['doc.read'])
        assert r.status_code == 201


# ============================================================
# 文档 RBAC 安全
# ============================================================

class TestDocumentRBACEdgeCases:
    def test_delete_requires_permission(self, client, admin_token):
        _create_role(client, admin_token, 'editor', ['doc.read', 'doc.write'])
        roles = client.get('/roles', headers=_auth(admin_token)).json['data']
        editor_id = next(r['id'] for r in roles if r['name'] == 'editor')
        client.post('/users/2/roles', json={'role_id': editor_id},
                   headers=_auth(admin_token))
        bob_token = _login(client, 'bob_editor')

        c = client.post('/documents', json={'title': 't', 'content': 'c'},
                       headers=_auth(bob_token))
        doc_id = c.json['data']['id']
        d = client.delete(f'/documents/{doc_id}', headers=_auth(bob_token))
        assert d.status_code == 403

    def test_delete_with_permission(self, client, admin_token):
        _create_role(client, admin_token, 'manager', ['doc.read', 'doc.write', 'doc.delete'])
        roles = client.get('/roles', headers=_auth(admin_token)).json['data']
        manager_id = next(r['id'] for r in roles if r['name'] == 'manager')
        client.post('/users/2/roles', json={'role_id': manager_id},
                   headers=_auth(admin_token))
        bob_token = _login(client, 'bob_editor')
        c = client.post('/documents', json={'title': 't', 'content': 'c'},
                       headers=_auth(bob_token))
        doc_id = c.json['data']['id']
        d = client.delete(f'/documents/{doc_id}', headers=_auth(bob_token))
        assert d.status_code == 200

    def test_get_nonexistent_document(self, client, admin_token):
        resp = client.get('/documents/99999', headers=_auth(admin_token))
        assert resp.status_code == 404


# ============================================================
# 权限继承深度
# ============================================================

class TestPermissionInheritanceDepth:
    def test_diamond_inheritance(self, client, admin_token):
        """钻石继承：权限是 set 而非 count"""
        a = _create_role(client, admin_token, 'base', ['doc.read'])
        a_id = a.json['data']['id']
        b = _create_role(client, admin_token, 'left', [], parent_role_id=a_id)
        b_id = b.json['data']['id']
        c = _create_role(client, admin_token, 'right', [], parent_role_id=a_id)
        c_id = c.json['data']['id']

        client.post('/users/4/roles', json={'role_id': b_id},
                   headers=_auth(admin_token))
        client.post('/users/4/roles', json={'role_id': c_id},
                   headers=_auth(admin_token))
        dave_token = _login(client, 'dave_noroles')
        assert client.get('/documents', headers=_auth(dave_token)).status_code == 200

    def test_remove_middle_role_keeps_others(self, client, admin_token):
        """用户有两个角色，移除一个后另一个仍有效"""
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

        client.delete(f'/users/2/roles/{r2_id}', headers=_auth(admin_token))
        bob_token = _login(client, 'bob_editor')
        assert client.get('/documents', headers=_auth(bob_token)).status_code == 200
        assert client.post('/documents', json={'title': 't2', 'content': 'c2'},
                          headers=_auth(bob_token)).status_code == 403
