"""
T2-1 博客系统测试（多模块版本）

测试标签 CRUD、文章绑定标签、按标签筛选文章。
"""

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'starter'))

from app import create_app, db
from models import Article, Tag


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


@pytest.fixture
def sample_article(client):
    """创建一篇示例文章"""
    with client.application.app_context():
        a = Article(title='测试文章', body='文章内容')
        db.session.add(a)
        db.session.commit()
        return a.id


# ============================================================
# 文章接口测试
# ============================================================

class TestArticleCRUD:
    def test_create_article(self, client):
        """创建文章"""
        resp = client.post('/articles', json={'title': 'Hello', 'body': 'World'})
        assert resp.status_code == 201
        assert resp.json['status'] == 'ok'
        assert resp.json['data']['title'] == 'Hello'

    def test_list_articles(self, client):
        """列出所有文章"""
        client.post('/articles', json={'title': 'A1', 'body': 'B1'})
        client.post('/articles', json={'title': 'A2', 'body': 'B2'})
        resp = client.get('/articles')
        assert resp.status_code == 200
        assert len(resp.json['data']) == 2

    def test_get_article(self, client):
        """获取单篇文章"""
        r = client.post('/articles', json={'title': 'Test', 'body': 'Body'})
        aid = r.json['data']['id']
        resp = client.get(f'/articles/{aid}')
        assert resp.status_code == 200
        assert resp.json['data']['title'] == 'Test'

    def test_create_article_missing_fields(self, client):
        """缺少必填字段应失败"""
        resp = client.post('/articles', json={'title': 'X'})
        assert resp.status_code == 400


# ============================================================
# 标签 CRUD 测试
# ============================================================

class TestTagCRUD:
    def test_create_tag(self, client):
        """创建标签"""
        resp = client.post('/tags', json={'name': 'Python'})
        assert resp.status_code == 201
        assert resp.json['data']['name'] == 'Python'

    def test_create_tag_duplicate(self, client):
        """创建重复标签应失败"""
        client.post('/tags', json={'name': 'Python'})
        resp = client.post('/tags', json={'name': 'Python'})
        assert resp.status_code == 409

    def test_create_tag_no_name(self, client):
        """name 为空应失败"""
        resp = client.post('/tags', json={})
        assert resp.status_code == 400

    def test_list_tags(self, client):
        """获取标签列表"""
        client.post('/tags', json={'name': 'Python'})
        client.post('/tags', json={'name': 'Flask'})
        resp = client.get('/tags')
        assert resp.status_code == 200
        assert len(resp.json['data']) == 2

    def test_update_tag(self, client):
        """编辑标签名称"""
        r = client.post('/tags', json={'name': 'Pytohn'})
        tid = r.json['data']['id']
        resp = client.put(f'/tags/{tid}', json={'name': 'Python'})
        assert resp.status_code == 200
        assert resp.json['data']['name'] == 'Python'

    def test_delete_tag(self, client):
        """删除标签"""
        r = client.post('/tags', json={'name': 'Python'})
        tid = r.json['data']['id']
        resp = client.delete(f'/tags/{tid}')
        assert resp.status_code == 200
        # 确认已删除
        list_resp = client.get('/tags')
        assert len(list_resp.json['data']) == 0


# ============================================================
# 文章绑定标签测试
# ============================================================

class TestArticleTagBinding:
    def test_bind_tags_to_article(self, client, sample_article):
        """为文章绑定标签"""
        t1 = client.post('/tags', json={'name': 'Python'}).json['data']
        t2 = client.post('/tags', json={'name': 'Flask'}).json['data']
        resp = client.post(f'/articles/{sample_article}/tags',
                          json={'tag_ids': [t1['id'], t2['id']]})
        assert resp.status_code == 200

    def test_get_article_tags(self, client, sample_article):
        """获取文章的标签"""
        t = client.post('/tags', json={'name': 'Python'}).json['data']
        client.post(f'/articles/{sample_article}/tags',
                   json={'tag_ids': [t['id']]})
        resp = client.get(f'/articles/{sample_article}/tags')
        assert resp.status_code == 200
        assert len(resp.json['data']) == 1
        assert resp.json['data'][0]['name'] == 'Python'

    def test_unbind_tag_from_article(self, client, sample_article):
        """解除文章与标签的关联"""
        t = client.post('/tags', json={'name': 'Python'}).json['data']
        client.post(f'/articles/{sample_article}/tags',
                   json={'tag_ids': [t['id']]})
        resp = client.delete(f'/articles/{sample_article}/tags/{t["id"]}')
        assert resp.status_code == 200
        tags = client.get(f'/articles/{sample_article}/tags').json['data']
        assert len(tags) == 0

    def test_delete_tag_removes_bindings(self, client, sample_article):
        """删除标签时应同时解除与文章的关联"""
        t = client.post('/tags', json={'name': 'Python'}).json['data']
        client.post(f'/articles/{sample_article}/tags',
                   json={'tag_ids': [t['id']]})
        client.delete(f'/tags/{t["id"]}')
        tags = client.get(f'/articles/{sample_article}/tags').json['data']
        assert len(tags) == 0


# ============================================================
# 按标签筛选文章测试
# ============================================================

class TestFilterArticlesByTag:
    def test_filter_by_tag_name(self, client):
        """按标签名称筛选文章"""
        a1 = client.post('/articles', json={'title': '文章1', 'body': '内容1'}).json['data']
        client.post('/articles', json={'title': '文章2', 'body': '内容2'})
        t = client.post('/tags', json={'name': 'Python'}).json['data']
        client.post(f'/articles/{a1["id"]}/tags', json={'tag_ids': [t['id']]})

        resp = client.get('/articles?tag=Python')
        assert resp.status_code == 200
        assert len(resp.json['data']) == 1
        assert resp.json['data'][0]['title'] == '文章1'

    def test_filter_by_tag_id(self, client):
        """按标签 ID 筛选文章"""
        a = client.post('/articles', json={'title': '文章A', 'body': '内容A'}).json['data']
        t = client.post('/tags', json={'name': 'Flask'}).json['data']
        client.post(f'/articles/{a["id"]}/tags', json={'tag_ids': [t['id']]})

        resp = client.get(f'/articles?tag_id={t["id"]}')
        assert resp.status_code == 200
        assert len(resp.json['data']) == 1

    def test_filter_no_match(self, client):
        """筛选无匹配结果时返回空列表"""
        client.post('/articles', json={'title': '文章', 'body': '内容'})
        resp = client.get('/articles?tag=NonExistent')
        assert resp.status_code == 200
        assert len(resp.json['data']) == 0

    def test_no_filter_returns_all(self, client):
        """不传筛选参数时返回所有文章"""
        client.post('/articles', json={'title': '文章1', 'body': '内容1'})
        client.post('/articles', json={'title': '文章2', 'body': '内容2'})
        resp = client.get('/articles')
        assert len(resp.json['data']) == 2
