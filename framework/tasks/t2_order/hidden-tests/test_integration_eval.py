"""
T2-2 订单系统隐藏评估测试（多模块版本）

这些测试对 Agent 不可见，用于最终评估。
覆盖：多模块集成一致性、跨模块数据完整性、接口对齐。
"""

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'starter'))

from app import create_app, db
from models import Product, Order, OrderItem, PaymentRequest


@pytest.fixture
def client():
    app = create_app()
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'

    with app.test_client() as c:
        with app.app_context():
            db.drop_all()
            db.create_all()
        yield c


def _seed_product(client, name='测试商品', price=99.9, stock=10):
    with client.application.app_context():
        p = Product(name=name, price=price, stock=stock)
        db.session.add(p)
        db.session.commit()
        return p.id


# ============================================================
# 多模块集成测试
# ============================================================

class TestMultiModuleIntegration:
    def test_app_starts_successfully(self, client):
        """app.py 正常启动且路由注册正确"""
        assert client.get('/products').status_code == 200
        assert client.get('/orders').status_code == 200

    def test_models_importable(self, client):
        """models.py 的模型可正确导入"""
        with client.application.app_context():
            db.session.add(Product(name='Test', price=1.0, stock=1))
            db.session.commit()
            assert Product.query.count() == 1

    def test_both_blueprints_registered(self, client):
        """product_bp 和 order_bp 都正确注册"""
        assert client.post('/products', json={'name': 'X', 'price': 1, 'stock': 1}).status_code == 201
        assert client.post('/orders', json={'user_id': 'u1', 'items': []}).status_code == 400


# ============================================================
# 跨模块数据一致性
# ============================================================

class TestCrossModuleConsistency:
    def test_order_items_reference_correct_product(self, client):
        """OrderItem 的 unit_price 应使用 Product.price 的快照"""
        pid = _seed_product(client, name='A', price=100.0, stock=10)
        resp = client.post('/orders', json={
            'user_id': 'u1',
            'items': [{'product_id': pid, 'quantity': 2}]
        })
        order_id = resp.json['data']['id']

        # 获取订单详情，检查 items
        detail = client.get(f'/orders/{order_id}').json['data']
        assert len(detail['items']) == 1
        assert detail['items'][0]['unit_price'] == 100.0
        assert detail['items'][0]['product_id'] == pid

    def test_stock_deduction_cross_module(self, client):
        """routes_order.py 付款扣库存应正确反映在 routes_product.py"""
        pid = _seed_product(client, stock=10)
        resp = client.post('/orders', json={
            'user_id': 'u1',
            'items': [{'product_id': pid, 'quantity': 3}]
        })
        order_id = resp.json['data']['id']
        client.post(f'/orders/{order_id}/pay', headers={'Idempotency-Key': 'cross-1'})

        # 通过 product_bp 检查库存
        product = client.get(f'/products/{pid}').json['data']
        assert product['stock'] == 7

    def test_cancel_restores_stock_cross_module(self, client):
        """取消已付款订单，库存应正确恢复"""
        pid = _seed_product(client, stock=10)
        resp = client.post('/orders', json={
            'user_id': 'u1',
            'items': [{'product_id': pid, 'quantity': 5}]
        })
        order_id = resp.json['data']['id']
        client.post(f'/orders/{order_id}/pay', headers={'Idempotency-Key': 'cross-2'})
        client.post(f'/orders/{order_id}/cancel')

        product = client.get(f'/products/{pid}').json['data']
        assert product['stock'] == 10

    def test_total_amount_matches_items(self, client):
        """total_amount 应等于各 item 的 unit_price * quantity 之和"""
        p1_id = _seed_product(client, name='A', price=19.99, stock=10)
        p2_id = _seed_product(client, name='B', price=29.99, stock=10)
        resp = client.post('/orders', json={
            'user_id': 'u1',
            'items': [
                {'product_id': p1_id, 'quantity': 3},
                {'product_id': p2_id, 'quantity': 2}
            ]
        })
        data = resp.json['data']
        assert abs(data['total_amount'] - 119.95) < 0.01


# ============================================================
# 接口对齐测试
# ============================================================

class TestInterfaceAlignment:
    def test_order_status_matches_model(self, client):
        """订单状态值应与 models.py 中定义的一致"""
        pid = _seed_product(client)
        resp = client.post('/orders', json={
            'user_id': 'u1',
            'items': [{'product_id': pid, 'quantity': 1}]
        })
        assert resp.json['data']['status'] == 'pending'

    def test_order_detail_contains_items_list(self, client):
        """订单详情应包含 items（models.py 中的 OrderItem）"""
        pid = _seed_product(client)
        resp = client.post('/orders', json={
            'user_id': 'u1',
            'items': [{'product_id': pid, 'quantity': 2}]
        })
        detail = client.get(f'/orders/{resp.json["data"]["id"]}').json['data']
        assert 'items' in detail
        assert len(detail['items']) == 1

    def test_product_response_fields_match_model(self, client):
        """产品路由返回的字段应与 models.py 一致"""
        pid = _seed_product(client, name='Test', price=50.0, stock=5)
        data = client.get(f'/products/{pid}').json['data']
        assert data['id'] == pid
        assert data['name'] == 'Test'
        assert data['price'] == 50.0
        assert data['stock'] == 5


# ============================================================
# 订单 CRUD 边界条件
# ============================================================

class TestOrderCRUDEdgeCases:
    def test_create_order_nonexistent_product(self, client):
        """引用不存在的商品应失败"""
        resp = client.post('/orders', json={
            'user_id': 'u1',
            'items': [{'product_id': 99999, 'quantity': 1}]
        })
        assert resp.status_code == 400

    def test_create_order_zero_quantity(self, client):
        """购买数量为 0 应被拒绝"""
        pid = _seed_product(client)
        resp = client.post('/orders', json={
            'user_id': 'u1',
            'items': [{'product_id': pid, 'quantity': 0}]
        })
        assert resp.status_code == 400

    def test_create_order_negative_quantity(self, client):
        """购买数量为负数应被拒绝"""
        pid = _seed_product(client)
        resp = client.post('/orders', json={
            'user_id': 'u1',
            'items': [{'product_id': pid, 'quantity': -1}]
        })
        assert resp.status_code == 400

    def test_create_order_empty_items(self, client):
        """空 items 列表应被拒绝"""
        resp = client.post('/orders', json={
            'user_id': 'u1',
            'items': []
        })
        assert resp.status_code == 400

    def test_get_nonexistent_order(self, client):
        """查询不存在的订单应返回 404"""
        resp = client.get('/orders/99999')
        assert resp.status_code == 404


# ============================================================
# 状态机边界路径
# ============================================================

class TestStateMachineEdgeCases:
    def test_cancel_pending_order(self, client):
        """pending 状态可以直接取消"""
        pid = _seed_product(client)
        resp = client.post('/orders', json={
            'user_id': 'u1',
            'items': [{'product_id': pid, 'quantity': 1}]
        })
        order_id = resp.json['data']['id']
        cancel = client.post(f'/orders/{order_id}/cancel')
        assert cancel.status_code == 200
        assert cancel.json['data']['status'] == 'cancelled'

    def test_cancel_already_cancelled(self, client):
        """已取消订单再次操作返回 409"""
        pid = _seed_product(client)
        resp = client.post('/orders', json={
            'user_id': 'u1',
            'items': [{'product_id': pid, 'quantity': 1}]
        })
        order_id = resp.json['data']['id']
        client.post(f'/orders/{order_id}/cancel')
        resp2 = client.post(f'/orders/{order_id}/cancel')
        assert resp2.status_code == 409

    def test_shipped_cannot_pay(self, client):
        """shipped 状态不能再次支付"""
        pid = _seed_product(client)
        resp = client.post('/orders', json={
            'user_id': 'u1',
            'items': [{'product_id': pid, 'quantity': 1}]
        })
        order_id = resp.json['data']['id']
        client.post(f'/orders/{order_id}/pay', headers={'Idempotency-Key': 'edge-1'})
        client.post(f'/orders/{order_id}/ship')
        resp = client.post(f'/orders/{order_id}/pay', headers={'Idempotency-Key': 'edge-2'})
        assert resp.status_code == 409

    def test_stock_cannot_go_negative(self, client):
        """库存不能透支"""
        pid = _seed_product(client, stock=10)

        # 创建两个各买 8 个的订单
        r1 = client.post('/orders', json={
            'user_id': 'u1',
            'items': [{'product_id': pid, 'quantity': 8}]
        })
        r2 = client.post('/orders', json={
            'user_id': 'u2',
            'items': [{'product_id': pid, 'quantity': 8}]
        })

        # 第一个付款成功
        client.post(f'/orders/{r1.json["data"]["id"]}/pay',
                   headers={'Idempotency-Key': 'neg-1'})

        # 第二个付款应失败（库存不足）
        pay2 = client.post(f'/orders/{r2.json["data"]["id"]}/pay',
                          headers={'Idempotency-Key': 'neg-2'})
        assert pay2.status_code == 400

        # 库存应为 2
        product = client.get(f'/products/{pid}').json['data']
        assert product['stock'] == 2


# ============================================================
# 库存边界
# ============================================================

class TestInventoryEdgeCases:
    def test_create_order_does_not_deduct_stock(self, client):
        """创建订单（未付款）不应扣减库存"""
        pid = _seed_product(client, stock=10)
        client.post('/orders', json={
            'user_id': 'u1',
            'items': [{'product_id': pid, 'quantity': 5}]
        })
        product = client.get(f'/products/{pid}').json['data']
        assert product['stock'] == 10

    def test_stock_exact_zero(self, client):
        """库存恰好用完"""
        pid = _seed_product(client, stock=10)
        resp = client.post('/orders', json={
            'user_id': 'u1',
            'items': [{'product_id': pid, 'quantity': 10}]
        })
        order_id = resp.json['data']['id']
        client.post(f'/orders/{order_id}/pay', headers={'Idempotency-Key': 'exact'})

        product = client.get(f'/products/{pid}').json['data']
        assert product['stock'] == 0

        # 再下单应失败
        resp2 = client.post('/orders', json={
            'user_id': 'u2',
            'items': [{'product_id': pid, 'quantity': 1}]
        })
        assert resp2.status_code == 400


# ============================================================
# 数据完整性
# ============================================================

class TestDataIntegrity:
    def test_order_contains_correct_items(self, client):
        """订单详情应包含正确的 items 列表"""
        p1_id = _seed_product(client, name='A', price=10.0, stock=10)
        p2_id = _seed_product(client, name='B', price=20.0, stock=10)

        resp = client.post('/orders', json={
            'user_id': 'u1',
            'items': [
                {'product_id': p1_id, 'quantity': 2},
                {'product_id': p2_id, 'quantity': 3}
            ]
        })
        detail = client.get(f'/orders/{resp.json["data"]["id"]}').json['data']
        assert len(detail['items']) == 2

    def test_order_has_created_at(self, client):
        """订单应有 created_at 时间戳"""
        pid = _seed_product(client)
        resp = client.post('/orders', json={
            'user_id': 'u1',
            'items': [{'product_id': pid, 'quantity': 1}]
        })
        assert resp.json['data']['created_at'] is not None
