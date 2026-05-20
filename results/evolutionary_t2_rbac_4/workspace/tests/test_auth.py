"""
ATU-001: POST /login 登录接口单元测试

验证用户名密码，返回 JWT（含 user_id + tenant_id + exp）。

覆盖场景:
1. 正常登录 -> 200 + 有效 JWT（含 user_id, tenant_id, exp）
2. 密码错误 -> 401
3. 用户名不存在 -> 401
4. 缺少 username 或 password -> 400
5. JWT payload 验证（解码 token 检查字段）
"""

import os
import sys
import datetime

import pytest
import jwt as pyjwt

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'starter'))

from app import create_app, db
from models import Tenant, User
from middleware import hash_password


@pytest.fixture
def client():
    """创建测试客户端 + ATU-001 所需的种子数据。"""
    app = create_app()
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    app.config['JWT_SECRET'] = 'test-secret'
    app.config['JWT_EXPIRY_HOURS'] = 24

    with app.test_client() as c:
        with app.app_context():
            db.drop_all()
            db.create_all()
            # -- 种子数据 --
            db.session.add(Tenant(id=1, name='TenantA'))
            db.session.add(
                User(id=1, tenant_id=1, username='alice',
                     password_hash=hash_password('pw'))
            )
            db.session.commit()
        yield c


# ============================================================
# ATU-001 测试用例
# ============================================================


class TestLogin:
    """POST /login 端点测试。"""

    def test_login_success_returns_200_and_token(self, client):
        """正常登录 -> 200 + 返回 token。"""
        resp = client.post('/login', json={'username': 'alice', 'password': 'pw'})

        assert resp.status_code == 200
        data = resp.get_json()
        assert data['status'] == 'ok'
        assert 'token' in data['data']
        assert isinstance(data['data']['token'], str)

    def test_login_success_jwt_contains_required_fields(self, client):
        """正常登录 -> JWT payload 包含 user_id, tenant_id, exp。"""
        resp = client.post('/login', json={'username': 'alice', 'password': 'pw'})
        assert resp.status_code == 200

        token = resp.get_json()['data']['token']
        payload = pyjwt.decode(token, 'test-secret', algorithms=['HS256'])

        assert payload['user_id'] == 1
        assert payload['tenant_id'] == 1
        assert 'exp' in payload
        # exp 应该是未来的时间戳（秒级 Unix 时间）
        assert payload['exp'] > datetime.datetime.utcnow().timestamp()

    def test_login_wrong_password_returns_401(self, client):
        """密码错误 -> 401。"""
        resp = client.post('/login', json={'username': 'alice', 'password': 'wrong'})

        assert resp.status_code == 401
        data = resp.get_json()
        assert data['status'] == 'error'

    def test_login_nonexistent_user_returns_401(self, client):
        """用户名不存在 -> 401。"""
        resp = client.post('/login', json={'username': 'nobody', 'password': 'pw'})

        assert resp.status_code == 401
        data = resp.get_json()
        assert data['status'] == 'error'

    def test_login_missing_username_returns_400(self, client):
        """缺少 username -> 400。"""
        resp = client.post('/login', json={'password': 'pw'})

        assert resp.status_code == 400
        data = resp.get_json()
        assert data['status'] == 'error'

    def test_login_missing_password_returns_400(self, client):
        """缺少 password -> 400。"""
        resp = client.post('/login', json={'username': 'alice'})

        assert resp.status_code == 400
        data = resp.get_json()
        assert data['status'] == 'error'

    def test_login_missing_both_fields_returns_400(self, client):
        """同时缺少 username 和 password -> 400。"""
        resp = client.post('/login', json={})

        assert resp.status_code == 400
        data = resp.get_json()
        assert data['status'] == 'error'
