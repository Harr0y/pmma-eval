"""
T3 微型电商系统隐藏评估测试（多模块版本）

这些测试对 Agent 不可见，用于最终评估。
覆盖：需求变更验证、安全性、数据完整性、多模块集成。
"""

import os
import sys
import time
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'starter'))

from app import create_app, db
from models import User, Product, Order


@pytest.fixture
def client():
    app = create_app()
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    with app.test_client() as c:
        with app.app_context():
            db.drop_all()
            db.create_all()
            db.session.add(User(username='admin', role='admin'))
            db.session.add(User(username='user1', role='user'))
            db.session.commit()
        yield c


def _auth(user_id):
    return {'X-User-Id': str(user_id)}


def _seed_product(client, name='TestItem', price=10.0, stock=10):
    with client.application.app_context():
        p = Product(name=name, price=price, stock=stock)
        db.session.add(p)
        db.session.commit()
        return p.id


# ============================================================
# 基础功能完整性（多模块集成）
# ============================================================

class TestMultiModuleIntegration:
    def test_app_starts_successfully(self, client):
        """app.py 能正常启动且路由注册正确"""
        res = client.get('/products')
        assert res.status_code == 200

    def test_models_importable(self, client):
        """models.py 的模型可以被正确导入和使用"""
        with client.application.app_context():
            db.session.add(Product(name='Test', price=1.0, stock=1))
            db.session.commit()
            p = Product.query.first()
            assert p.name == 'Test'

    def test_middleware_auth_works(self, client):
        """middleware.py 的认证正常工作"""
        res = client.post('/products', json={
            'name': 'X', 'price': 1.0, 'stock': 1
        })
        assert res.status_code in (400, 401, 403)


# ============================================================
# 需求变更 1：订单 origin 字段
# ============================================================

class TestOrderOrigin:
    def test_order_has_origin_field(self, client):
        """订单应包含 origin 字段，默认为 'web'"""
        pid = _seed_product(client)
        res = client.post('/orders', json={
            'product_id': pid, 'quantity': 1
        }, headers=_auth(2))
        assert res.status_code in (200, 201)
        assert res.json['data'].get('origin') == 'web'

    def test_order_with_custom_origin(self, client):
        """可以指定订单 origin"""
        pid = _seed_product(client)
        res = client.post('/orders', json={
            'product_id': pid, 'quantity': 1, 'origin': 'app'
        }, headers=_auth(2))
        assert res.status_code in (200, 201)
        assert res.json['data'].get('origin') == 'app'

    def test_order_query_returns_origin(self, client):
        """订单查询接口应返回 origin"""
        pid = _seed_product(client)
        client.post('/orders', json={
            'product_id': pid, 'quantity': 1
        }, headers=_auth(2))

        res = client.get('/orders', headers=_auth(1))
        assert res.status_code == 200
        orders = res.json['data']
        assert len(orders) >= 1
        assert 'origin' in orders[0]


# ============================================================
# 需求变更 2：高频下单限流
# ============================================================

class TestRateLimiting:
    def test_rapid_orders_blocked(self, client):
        """同一用户 10 秒内只能成功提交 1 笔订单"""
        pid = _seed_product(client, stock=100)
        res1 = client.post('/orders', json={
            'product_id': pid, 'quantity': 1
        }, headers=_auth(2))
        assert res1.status_code in (200, 201)

        res2 = client.post('/orders', json={
            'product_id': pid, 'quantity': 1
        }, headers=_auth(2))
        assert res2.status_code == 429

    def test_different_users_not_limited(self, client):
        """不同用户不受同一限流规则影响"""
        pid = _seed_product(client, stock=100)
        with client.application.app_context():
            db.session.add(User(username='user2', role='user'))
            db.session.commit()

        res1 = client.post('/orders', json={
            'product_id': pid, 'quantity': 1
        }, headers=_auth(2))
        assert res1.status_code in (200, 201)

        res2 = client.post('/orders', json={
            'product_id': pid, 'quantity': 1
        }, headers=_auth(3))
        assert res2.status_code in (200, 201)


# ============================================================
# 需求变更 3：库存扣减原子性
# ============================================================

class TestAtomicStock:
    def test_stock_cannot_go_negative(self, client):
        """并发下单时库存不能为负"""
        pid = _seed_product(client, stock=2)
        res1 = client.post('/orders', json={
            'product_id': pid, 'quantity': 2
        }, headers=_auth(2))
        assert res1.status_code in (200, 201)

        with client.application.app_context():
            db.session.add(User(username='user2', role='user'))
            db.session.commit()

        res2 = client.post('/orders', json={
            'product_id': pid, 'quantity': 1
        }, headers=_auth(3))
        assert res2.json['status'] == 'error'

        with client.application.app_context():
            p = Product.query.get(pid)
            assert p.stock == 0

    def test_exact_stock_depletion(self, client):
        """恰好用完库存"""
        pid = _seed_product(client, stock=3)
        res = client.post('/orders', json={
            'product_id': pid, 'quantity': 3
        }, headers=_auth(2))
        assert res.status_code in (200, 201)

        with client.application.app_context():
            p = Product.query.get(pid)
            assert p.stock == 0

    def test_zero_stock_product_order_fails(self, client):
        """库存为 0 的商品不能下单"""
        pid = _seed_product(client, stock=0)
        res = client.post('/orders', json={
            'product_id': pid, 'quantity': 1
        }, headers=_auth(2))
        assert res.json['status'] == 'error'


# ============================================================
# 安全性边界
# ============================================================

class TestSecurityEdgeCases:
    def test_order_with_negative_quantity(self, client):
        """负数购买量应被拒绝"""
        pid = _seed_product(client)
        res = client.post('/orders', json={
            'product_id': pid, 'quantity': -1
        }, headers=_auth(2))
        assert res.status_code in (400, 422)

    def test_order_with_zero_quantity(self, client):
        """零购买量应被拒绝"""
        pid = _seed_product(client)
        res = client.post('/orders', json={
            'product_id': pid, 'quantity': 0
        }, headers=_auth(2))
        assert res.status_code in (400, 422)

    def test_order_with_missing_fields(self, client):
        """缺少必要字段应返回错误"""
        res = client.post('/orders', json={}, headers=_auth(2))
        assert res.status_code in (400, 422)

    def test_no_user_id_order(self, client):
        """缺少 X-User-Id 时下单应失败"""
        pid = _seed_product(client)
        res = client.post('/orders', json={
            'product_id': pid, 'quantity': 1
        })
        assert res.status_code in (400, 401, 403)

    def test_user_cannot_modify_product(self, client):
        """普通用户不能修改产品"""
        pid = _seed_product(client)
        res = client.put(f'/products/{pid}', json={
            'price': 0.01
        }, headers=_auth(2))
        assert res.status_code in (403, 404, 405)


# ============================================================
# 数据完整性
# ============================================================

class TestDataIntegrity:
    def test_order_links_correct_product(self, client):
        """订单应正确关联产品"""
        pid = _seed_product(client, name='SpecialItem', price=42.0, stock=10)
        res = client.post('/orders', json={
            'product_id': pid, 'quantity': 2
        }, headers=_auth(2))
        assert res.json['data']['product_id'] == pid
        assert abs(res.json['data']['total_price'] - 84.0) < 0.01

    def test_user_order_list_correct_user(self, client):
        """用户订单列表只包含自己的订单"""
        pid = _seed_product(client, stock=100)
        with client.application.app_context():
            db.session.add(User(username='user2', role='user'))
            db.session.commit()

        client.post('/orders', json={
            'product_id': pid, 'quantity': 1
        }, headers=_auth(2))
        client.post('/orders', json={
            'product_id': pid, 'quantity': 1
        }, headers=_auth(3))

        res = client.get('/orders', headers=_auth(2))
        orders = res.json['data']
        assert all(o['user_id'] == 2 for o in orders)
