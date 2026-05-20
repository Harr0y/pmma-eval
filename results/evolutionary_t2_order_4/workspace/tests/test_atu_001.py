"""
ATU-001 商品 CRUD 路由测试

独立测试文件，覆盖商品创建、列表、详情三个接口。
"""

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'starter'))

from app import create_app, db
from models import Product


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
