"""
ATU-001 — POST /login 接口单元测试

覆盖场景:
- 成功登录返回 JWT token
- JWT 包含 user_id 和 tenant_id
- 缺少 username 返回 400
- 缺少 password 返回 400
- 用户名不存在返回 401
- 密码错误返回 401
"""

import os
import sys

import pytest
import jwt as pyjwt

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'starter'))

from app import create_app, db
from models import Tenant, User, Role, Permission, user_roles, role_permissions
from middleware import hash_password


@pytest.fixture
def client():
    """创建测试客户端 + 种子数据（Tenant, User, Role, Permission）"""
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

            # --- Users (password = 'correct_password') ---
            pw = hash_password('correct_password')
            db.session.add(User(
                id=1, tenant_id=1, username='alice', password_hash=pw,
            ))
            db.session.add(User(
                id=2, tenant_id=1, username='bob', password_hash=pw,
            ))
            db.session.add(User(
                id=3, tenant_id=2, username='eve', password_hash=pw,
            ))

            # --- Permissions ---
            perm_codes = ['doc.read', 'doc.write', 'doc.delete', 'role.manage']
            for code in perm_codes:
                db.session.add(Permission(code=code))
            db.session.flush()

            # --- Roles ---
            db.session.add(Role(id=1, tenant_id=1, name='admin'))
            db.session.add(Role(id=2, tenant_id=2, name='admin'))
            db.session.flush()

            # --- Assign all permissions to admin roles ---
            db.session.execute(
                role_permissions.insert().from_select(
                    ['role_id', 'permission_id'],
                    db.session.query(db.literal(1), Permission.id)
                    .union_all(
                        db.session.query(db.literal(2), Permission.id)
                    ),
                )
            )

            # --- Assign admin role to alice (user 1) ---
            db.session.execute(
                user_roles.insert().values(user_id=1, role_id=1)
            )

            db.session.commit()
        yield c


# ============================================================
# 成功场景
# ============================================================


class TestLoginSuccess:
    """ATU-001 成功登录"""

    def test_login_returns_200_with_token(self, client):
        """正确凭证 → 200 + token"""
        resp = client.post('/login', json={
            'username': 'alice',
            'password': 'correct_password',
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['status'] == 'ok'
        assert 'token' in data['data']
        assert isinstance(data['data']['token'], str)
        assert len(data['data']['token']) > 0

    def test_jwt_contains_user_id(self, client):
        """JWT payload 必须包含 user_id"""
        resp = client.post('/login', json={
            'username': 'alice',
            'password': 'correct_password',
        })
        token = resp.get_json()['data']['token']
        payload = pyjwt.decode(token, 'test-secret', algorithms=['HS256'])
        assert 'user_id' in payload
        assert payload['user_id'] == 1

    def test_jwt_contains_tenant_id(self, client):
        """JWT payload 必须包含 tenant_id"""
        resp = client.post('/login', json={
            'username': 'alice',
            'password': 'correct_password',
        })
        token = resp.get_json()['data']['token']
        payload = pyjwt.decode(token, 'test-secret', algorithms=['HS256'])
        assert 'tenant_id' in payload
        assert payload['tenant_id'] == 1

    def test_jwt_contains_exp(self, client):
        """JWT payload 必须包含 exp 字段"""
        resp = client.post('/login', json={
            'username': 'alice',
            'password': 'correct_password',
        })
        token = resp.get_json()['data']['token']
        payload = pyjwt.decode(token, 'test-secret', algorithms=['HS256'])
        assert 'exp' in payload

    def test_different_user_gets_correct_ids(self, client):
        """不同用户登录后 JWT 中的 user_id 和 tenant_id 应正确"""
        resp = client.post('/login', json={
            'username': 'eve',
            'password': 'correct_password',
        })
        assert resp.status_code == 200
        token = resp.get_json()['data']['token']
        payload = pyjwt.decode(token, 'test-secret', algorithms=['HS256'])
        assert payload['user_id'] == 3
        assert payload['tenant_id'] == 2


# ============================================================
# 400 Bad Request — 缺少必填字段
# ============================================================


class TestLoginMissingFields:
    """ATU-001 缺少必填字段 → 400"""

    def test_missing_username_returns_400(self, client):
        """缺少 username → 400"""
        resp = client.post('/login', json={
            'password': 'correct_password',
        })
        assert resp.status_code == 400

    def test_missing_password_returns_400(self, client):
        """缺少 password → 400"""
        resp = client.post('/login', json={
            'username': 'alice',
        })
        assert resp.status_code == 400

    def test_missing_both_fields_returns_400(self, client):
        """username 和 password 都缺失 → 400"""
        resp = client.post('/login', json={})
        assert resp.status_code == 400


# ============================================================
# 401 Unauthorized — 凭证错误
# ============================================================


class TestLoginInvalidCredentials:
    """ATU-001 用户不存在或密码错误 → 401"""

    def test_nonexistent_username_returns_401(self, client):
        """用户名不存在 → 401"""
        resp = client.post('/login', json={
            'username': 'nonexistent_user',
            'password': 'correct_password',
        })
        assert resp.status_code == 401

    def test_wrong_password_returns_401(self, client):
        """密码错误 → 401"""
        resp = client.post('/login', json={
            'username': 'alice',
            'password': 'wrong_password',
        })
        assert resp.status_code == 401

    def test_nonexistent_user_wrong_password_returns_401(self, client):
        """不存在的用户 + 错误密码 → 401"""
        resp = client.post('/login', json={
            'username': 'ghost',
            'password': 'nope',
        })
        assert resp.status_code == 401
