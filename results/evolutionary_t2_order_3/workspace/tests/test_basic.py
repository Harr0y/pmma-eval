"""
T2-2 订单系统测试（多模块版本）

测试订单 CRUD、状态机、库存扣减、幂等付款。
"""

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'starter'))

from app import create_app, db
from models import Product, Order, OrderItem


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
        yield c


def _seed_product(client, name='测试商品', price=99.9, stock=10):
    """创建测试商品"""
    with client.application.app_context():
        p = Product(name=name, price=price, stock=stock)
        db.session.add(p)
        db.session.commit()
        return p.id


# ============================================================
# 商品接口测试
# ============================================================

class TestProductCRUD:
    def test_create_product(self, client):
        """创建商品"""
        resp = client.post('/products', json={'name': 'Laptop', 'price': 1000, 'stock': 5})
        assert resp.status_code == 201
        assert resp.json['status'] == 'ok'

    def test_list_products(self, client):
        """列出所有商品"""
        _seed_product(client)
        resp = client.get('/products')
        assert resp.status_code == 200
        assert len(resp.json['data']) == 1

    def test_get_product(self, client):
        """获取单个商品"""
        pid = _seed_product(client)
        resp = client.get(f'/products/{pid}')
        assert resp.status_code == 200
        assert resp.json['data']['price'] == 99.9


# ============================================================
# 订单 CRUD 测试
# ============================================================

class TestOrderCRUD:
    def test_create_order(self, client):
        """创建订单成功"""
        pid = _seed_product(client)
        resp = client.post('/orders', json={
            'user_id': 'u1',
            'items': [{'product_id': pid, 'quantity': 2}]
        })
        assert resp.status_code == 201
        data = resp.json['data']
        assert data['status'] == 'pending'
        assert data['user_id'] == 'u1'

    def test_create_order_insufficient_stock(self, client):
        """库存不足时创建订单应失败"""
        pid = _seed_product(client, stock=1)
        resp = client.post('/orders', json={
            'user_id': 'u1',
            'items': [{'product_id': pid, 'quantity': 5}]
        })
        assert resp.status_code == 400

    def test_create_order_total_calculation(self, client):
        """多商品订单总价计算正确"""
        p1_id = _seed_product(client, name='A', price=100.0, stock=5)
        p2_id = _seed_product(client, name='B', price=200.0, stock=8)
        resp = client.post('/orders', json={
            'user_id': 'u1',
            'items': [
                {'product_id': p1_id, 'quantity': 2},
                {'product_id': p2_id, 'quantity': 3}
            ]
        })
        assert resp.status_code == 201
        assert abs(resp.json['data']['total_amount'] - 800.0) < 0.01

    def test_filter_orders(self, client):
        """按 user_id 和 status 筛选订单"""
        pid = _seed_product(client, stock=100)
        client.post('/orders', json={'user_id': 'u1', 'items': [{'product_id': pid, 'quantity': 1}]})
        client.post('/orders', json={'user_id': 'u1', 'items': [{'product_id': pid, 'quantity': 1}]})
        client.post('/orders', json={'user_id': 'u2', 'items': [{'product_id': pid, 'quantity': 1}]})

        resp = client.get('/orders?user_id=u1')
        assert len(resp.json['data']) == 2

        resp = client.get('/orders?status=pending')
        assert len(resp.json['data']) == 3


# ============================================================
# 状态机测试
# ============================================================

class TestStateMachine:
    def _create_order(self, client, pid, quantity=1):
        resp = client.post('/orders', json={
            'user_id': 'u1',
            'items': [{'product_id': pid, 'quantity': quantity}]
        })
        return resp.json['data']

    def test_pay_order(self, client):
        """支付订单（pending → paid）"""
        pid = _seed_product(client)
        order = self._create_order(client, pid)
        resp = client.post(f'/orders/{order["id"]}/pay',
                          headers={'Idempotency-Key': 'key-001'})
        assert resp.status_code == 200
        assert resp.json['data']['status'] == 'paid'

    def test_ship_order(self, client):
        """发货（paid → shipped）"""
        pid = _seed_product(client)
        order = self._create_order(client, pid)
        client.post(f'/orders/{order["id"]}/pay', headers={'Idempotency-Key': 'key-002'})
        resp = client.post(f'/orders/{order["id"]}/ship')
        assert resp.json['data']['status'] == 'shipped'

    def test_deliver_order(self, client):
        """送达（shipped → delivered）"""
        pid = _seed_product(client)
        order = self._create_order(client, pid)
        client.post(f'/orders/{order["id"]}/pay', headers={'Idempotency-Key': 'key-003'})
        client.post(f'/orders/{order["id"]}/ship')
        resp = client.post(f'/orders/{order["id"]}/deliver')
        assert resp.json['data']['status'] == 'delivered'

    def test_illegal_pending_to_shipped(self, client):
        """非法跳转：pending → shipped"""
        pid = _seed_product(client)
        order = self._create_order(client, pid)
        resp = client.post(f'/orders/{order["id"]}/ship')
        assert resp.status_code == 409

    def test_illegal_paid_to_delivered(self, client):
        """非法跳转：paid → delivered"""
        pid = _seed_product(client)
        order = self._create_order(client, pid)
        client.post(f'/orders/{order["id"]}/pay', headers={'Idempotency-Key': 'key-004'})
        resp = client.post(f'/orders/{order["id"]}/deliver')
        assert resp.status_code == 409

    def test_delivered_cannot_be_cancelled(self, client):
        """已送达不可取消"""
        pid = _seed_product(client)
        order = self._create_order(client, pid)
        client.post(f'/orders/{order["id"]}/pay', headers={'Idempotency-Key': 'key-005'})
        client.post(f'/orders/{order["id"]}/ship')
        client.post(f'/orders/{order["id"]}/deliver')
        resp = client.post(f'/orders/{order["id"]}/cancel')
        assert resp.status_code == 409


# ============================================================
# 库存测试
# ============================================================

class TestInventory:
    def test_pay_deducts_stock(self, client):
        """付款时扣减库存"""
        pid = _seed_product(client, stock=10)
        resp = client.post('/orders', json={
            'user_id': 'u1',
            'items': [{'product_id': pid, 'quantity': 3}]
        })
        order = resp.json['data']
        client.post(f'/orders/{order["id"]}/pay', headers={'Idempotency-Key': 'key-inv-1'})

        product = client.get(f'/products/{pid}').json['data']
        assert product['stock'] == 7

    def test_cancel_paid_restores_stock(self, client):
        """取消已付款订单回滚库存"""
        pid = _seed_product(client, stock=10)
        resp = client.post('/orders', json={
            'user_id': 'u1',
            'items': [{'product_id': pid, 'quantity': 3}]
        })
        order = resp.json['data']
        client.post(f'/orders/{order["id"]}/pay', headers={'Idempotency-Key': 'key-inv-2'})
        client.post(f'/orders/{order["id"]}/cancel')

        product = client.get(f'/products/{pid}').json['data']
        assert product['stock'] == 10

    def test_cancel_pending_no_stock_change(self, client):
        """取消 pending 订单不影响库存"""
        pid = _seed_product(client, stock=10)
        resp = client.post('/orders', json={
            'user_id': 'u1',
            'items': [{'product_id': pid, 'quantity': 3}]
        })
        order = resp.json['data']
        client.post(f'/orders/{order["id"]}/cancel')

        product = client.get(f'/products/{pid}').json['data']
        assert product['stock'] == 10


# ============================================================
# 幂等性测试
# ============================================================

class TestIdempotency:
    def test_duplicate_pay_same_key(self, client):
        """同一 Idempotency-Key 重复付款只扣一次库存"""
        pid = _seed_product(client, stock=10)
        resp = client.post('/orders', json={
            'user_id': 'u1',
            'items': [{'product_id': pid, 'quantity': 3}]
        })
        order = resp.json['data']

        client.post(f'/orders/{order["id"]}/pay', headers={'Idempotency-Key': 'same-key'})
        client.post(f'/orders/{order["id"]}/pay', headers={'Idempotency-Key': 'same-key'})

        product = client.get(f'/products/{pid}').json['data']
        assert product['stock'] == 7

    def test_different_key_different_request(self, client):
        """不同 key 视为不同请求"""
        pid = _seed_product(client, stock=10)
        resp = client.post('/orders', json={
            'user_id': 'u1',
            'items': [{'product_id': pid, 'quantity': 2}]
        })
        order = resp.json['data']

        client.post(f'/orders/{order["id"]}/pay', headers={'Idempotency-Key': 'key-a'})
        resp = client.post(f'/orders/{order["id"]}/pay', headers={'Idempotency-Key': 'key-b'})
        assert resp.status_code == 409

    def test_missing_idempotency_key(self, client):
        """缺少 Idempotency-Key 返回 400"""
        pid = _seed_product(client, stock=10)
        resp = client.post('/orders', json={
            'user_id': 'u1',
            'items': [{'product_id': pid, 'quantity': 1}]
        })
        order = resp.json['data']
        resp = client.post(f'/orders/{order["id"]}/pay')
        assert resp.status_code == 400
