"""
T3 微型电商系统测试（多模块版本）

测试产品管理、订单系统、用户角色 RBAC。
"""

import os
import sys
import pytest

# 将 starter 目录加入 path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'starter'))

from app import create_app, db
from models import User, Product, Order
from middleware import reset_rate_limits


@pytest.fixture
def client():
    """创建测试客户端"""
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
            reset_rate_limits()
        yield c


def _auth(user_id):
    return {'X-User-Id': str(user_id)}


# ============================================================
# 产品管理测试
# ============================================================

class TestProductManagement:
    def test_admin_can_create_product(self, client):
        """管理员可以创建产品"""
        res = client.post('/products', json={
            'name': 'Laptop',
            'price': 1000.0,
            'stock': 10
        }, headers=_auth(1))
        assert res.status_code in (200, 201)
        assert res.json['status'] == 'ok'

    def test_user_cannot_create_product(self, client):
        """普通用户不能创建产品"""
        res = client.post('/products', json={
            'name': 'Hacker Tool',
            'price': 0.0,
            'stock': 999
        }, headers=_auth(2))
        assert res.status_code == 403

    def test_list_products(self, client):
        """列出所有产品"""
        with client.application.app_context():
            db.session.add(Product(name='Mouse', price=50.0, stock=5))
            db.session.commit()

        res = client.get('/products')
        assert res.status_code == 200
        assert res.json['status'] == 'ok'
        assert len(res.json['data']) == 1

    def test_no_user_id_returns_error(self, client):
        """缺少 X-User-Id 时创建产品应失败"""
        res = client.post('/products', json={
            'name': 'X', 'price': 1.0, 'stock': 1
        })
        assert res.status_code in (400, 401, 403)


# ============================================================
# 订单系统测试
# ============================================================

class TestOrderSystem:
    def test_user_can_create_order(self, client):
        """用户可以下单"""
        with client.application.app_context():
            db.session.add(Product(name='Mouse', price=50.0, stock=5))
            db.session.commit()

        res = client.post('/orders', json={
            'product_id': 1, 'quantity': 2
        }, headers=_auth(2))
        assert res.status_code in (200, 201)
        assert res.json['status'] == 'ok'

    def test_order_deducts_stock(self, client):
        """下单时扣减库存"""
        with client.application.app_context():
            db.session.add(Product(name='Mouse', price=50.0, stock=5))
            db.session.commit()

        client.post('/orders', json={
            'product_id': 1, 'quantity': 2
        }, headers=_auth(2))

        with client.application.app_context():
            p = Product.query.get(1)
            assert p.stock == 3

    def test_insufficient_stock(self, client):
        """库存不足时下单应失败"""
        with client.application.app_context():
            db.session.add(Product(name='Rare Item', price=500.0, stock=1))
            db.session.commit()

        res = client.post('/orders', json={
            'product_id': 1, 'quantity': 5
        }, headers=_auth(2))
        assert res.json['status'] == 'error'

        with client.application.app_context():
            p = Product.query.get(1)
            assert p.stock == 1

    def test_admin_sees_all_orders(self, client):
        """管理员可以查看所有订单"""
        with client.application.app_context():
            db.session.add(Product(name='Item', price=10.0, stock=10))
            db.session.commit()

        client.post('/orders', json={
            'product_id': 1, 'quantity': 1
        }, headers=_auth(2))

        res = client.get('/orders', headers=_auth(1))
        assert res.status_code == 200
        assert len(res.json['data']) >= 1

    def test_user_sees_only_own_orders(self, client):
        """普通用户只能看自己的订单"""
        with client.application.app_context():
            db.session.add(User(username='user2', role='user'))
            db.session.add(Product(name='Item', price=10.0, stock=10))
            db.session.commit()

        client.post('/orders', json={
            'product_id': 1, 'quantity': 1
        }, headers=_auth(2))

        res = client.get('/orders', headers=_auth(2))
        assert res.status_code == 200
        assert all(o['user_id'] == 2 for o in res.json['data'])

    def test_order_total_price(self, client):
        """订单总价计算正确"""
        with client.application.app_context():
            db.session.add(Product(name='Item', price=25.0, stock=10))
            db.session.commit()

        res = client.post('/orders', json={
            'product_id': 1, 'quantity': 4
        }, headers=_auth(2))
        assert res.json['status'] == 'ok'
        assert abs(res.json['data']['total_price'] - 100.0) < 0.01

    def test_order_nonexistent_product(self, client):
        """购买不存在的产品应失败"""
        res = client.post('/orders', json={
            'product_id': 999, 'quantity': 1
        }, headers=_auth(2))
        assert res.status_code in (400, 404)


# ============================================================
# RBAC 测试
# ============================================================

class TestRBAC:
    def test_user_cannot_create_product(self, client):
        """普通用户不能创建产品"""
        res = client.post('/products', json={
            'name': 'X', 'price': 1.0, 'stock': 1
        }, headers=_auth(2))
        assert res.status_code == 403

    def test_admin_can_create_product(self, client):
        """管理员可以创建产品"""
        res = client.post('/products', json={
            'name': 'Y', 'price': 2.0, 'stock': 2
        }, headers=_auth(1))
        assert res.status_code in (200, 201)
