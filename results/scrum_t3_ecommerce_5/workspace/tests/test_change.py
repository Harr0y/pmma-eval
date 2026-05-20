"""
T3 需求变更测试（多模块版本）

验证 change.md 中的需求变更：origin 字段、限流、原子库存。
"""

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'starter'))

from app import create_app, db
from models import User, Product, Order
import middleware


@pytest.fixture
def client():
    middleware.reset_rate_limit()
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
# 变更 1：订单 origin 字段
# ============================================================

class TestOrderOrigin:
    def test_order_default_origin(self, client):
        """下单时未指定 origin，默认为 'web'"""
        pid = _seed_product(client)
        res = client.post('/orders', json={
            'product_id': pid, 'quantity': 1
        }, headers=_auth(2))
        assert res.status_code in (200, 201)
        assert res.json['data'].get('origin') == 'web'

    def test_order_custom_origin(self, client):
        """下单时可以指定 origin"""
        pid = _seed_product(client)
        res = client.post('/orders', json={
            'product_id': pid, 'quantity': 1, 'origin': 'app'
        }, headers=_auth(2))
        assert res.status_code in (200, 201)
        assert res.json['data'].get('origin') == 'app'


# ============================================================
# 变更 2：限流（10 秒内同一用户只能下一单）
# ============================================================

class TestRateLimiting:
    def test_rapid_order_blocked(self, client):
        """同一用户快速下两单，第二单应返回 429"""
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
        """不同用户不受限流影响"""
        pid = _seed_product(client, stock=100)
        with client.application.app_context():
            db.session.add(User(username='user2', role='user'))
            db.session.commit()

        res1 = client.post('/orders', json={
            'product_id': pid, 'quantity': 1
        }, headers=_auth(2))
        res2 = client.post('/orders', json={
            'product_id': pid, 'quantity': 1
        }, headers=_auth(3))
        assert res1.status_code in (200, 201)
        assert res2.status_code in (200, 201)


# ============================================================
# 变更 3：库存扣减原子性
# ============================================================

class TestAtomicStock:
    def test_stock_no_negative(self, client):
        """库存不能为负数"""
        pid = _seed_product(client, stock=1)
        res1 = client.post('/orders', json={
            'product_id': pid, 'quantity': 1
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

    def test_zero_stock_order_fails(self, client):
        """库存为 0 的商品不能下单"""
        pid = _seed_product(client, stock=0)
        res = client.post('/orders', json={
            'product_id': pid, 'quantity': 1
        }, headers=_auth(2))
        assert res.json['status'] == 'error'
