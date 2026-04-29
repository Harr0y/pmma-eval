"""
T2-1 博客系统隐藏评估测试（多模块版本）

这些测试对 Agent 不可见，用于最终评估。
覆盖：多模块集成一致性、跨模块数据完整性、接口对齐。
"""

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'starter'))

from app import create_app, db
from models import Article, Tag, article_tags


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
# 多模块集成测试
# ============================================================

class TestMultiModuleIntegration:
    def test_app_starts_successfully(self, client):
        """app.py 能正常启动且路由注册正确"""
        resp = client.get('/articles')
        assert resp.status_code == 200

    def test_models_importable(self, client):
        """models.py 的模型可以被正确导入和使用"""
        with client.application.app_context():
            db.session.add(Article(title='Test', body='Body'))
            db.session.add(Tag(name='TestTag'))
            db.session.commit()
            assert Article.query.count() == 1
            assert Tag.query.count() == 1

    def test_blueprint_registration(self, client):
        """两个 Blueprint 都正确注册"""
        # article_bp
        assert client.get('/articles').status_code == 200
        # tag_bp
        assert client.get('/tags').status_code == 200


# ============================================================
# 跨模块数据一致性
# ============================================================

class TestCrossModuleConsistency:
    def test_tag_deletion_cascades_to_articles(self, client, sample_article):
        """routes_tag.py 删除标签后，routes_article.py 的标签列表应同步更新"""
        t = client.post('/tags', json={'name': 'Python'}).json['data']
        client.post(f'/articles/{sample_article}/tags', json={'tag_ids': [t['id']]})

        # 确认绑定
        tags_before = client.get(f'/articles/{sample_article}/tags').json['data']
        assert len(tags_before) == 1

        # 通过 tag_bp 删除
        client.delete(f'/tags/{t["id"]}')

        # 通过 article_bp 检查 — 应该为空
        tags_after = client.get(f'/articles/{sample_article}/tags').json['data']
        assert len(tags_after) == 0

    def test_tag_filter_uses_correct_model(self, client):
        """routes_article.py 的标签筛选应使用 models.py 中的正确关系"""
        a1 = client.post('/articles', json={'title': 'A1', 'body': 'B1'}).json['data']
        a2 = client.post('/articles', json={'title': 'A2', 'body': 'B2'}).json['data']
        t = client.post('/tags', json={'name': 'Python'}).json['data']

        # 只给 a1 绑定
        client.post(f'/articles/{a1["id"]}/tags', json={'tag_ids': [t['id']]})

        # 筛选应只返回 a1
        resp = client.get('/articles?tag=Python')
        assert len(resp.json['data']) == 1
        assert resp.json['data'][0]['title'] == 'A1'

    def test_multiple_articles_same_tag(self, client):
        """一篇文章有多个标签时，不筛选不应重复"""
        a = client.post('/articles', json={'title': 'Multi', 'body': 'Body'}).json['data']
        t1 = client.post('/tags', json={'name': 'T1'}).json['data']
        t2 = client.post('/tags', json={'name': 'T2'}).json['data']
        client.post(f'/articles/{a["id"]}/tags', json={'tag_ids': [t1['id'], t2['id']]})

        resp = client.get('/articles')
        assert len(resp.json['data']) == 1  # 不应重复

    def test_article_with_multiple_tags_filtered_by_one(self, client):
        """一篇文章有多个标签，按其中一个筛选"""
        a = client.post('/articles', json={'title': 'Multi', 'body': 'Body'}).json['data']
        t1 = client.post('/tags', json={'name': 'Python'}).json['data']
        t2 = client.post('/tags', json={'name': 'Flask'}).json['data']
        client.post(f'/articles/{a["id"]}/tags', json={'tag_ids': [t1['id'], t2['id']]})

        resp = client.get('/articles?tag=Python')
        assert resp.status_code == 200
        assert len(resp.json['data']) == 1


# ============================================================
# 接口对齐测试
# ============================================================

class TestInterfaceAlignment:
    def test_tag_response_fields_match_model(self, client):
        """Tag 路由返回的字段应与 models.py 中定义一致"""
        r = client.post('/tags', json={'name': 'Python'})
        data = r.json['data']
        assert 'id' in data
        assert 'name' in data
        assert data['name'] == 'Python'

    def test_article_response_fields_match_model(self, client):
        """Article 路由返回的字段应与 models.py 中定义一致"""
        r = client.post('/articles', json={'title': 'Test', 'body': 'Body'})
        data = r.json['data']
        assert 'id' in data
        assert 'title' in data
        assert 'body' in data

    def test_article_tag_response_uses_tag_model(self, client, sample_article):
        """文章的标签列表应返回 Tag 模型的字段"""
        t = client.post('/tags', json={'name': 'Flask'}).json['data']
        client.post(f'/articles/{sample_article}/tags', json={'tag_ids': [t['id']]})

        tags = client.get(f'/articles/{sample_article}/tags').json['data']
        assert len(tags) == 1
        assert tags[0]['id'] == t['id']
        assert tags[0]['name'] == 'Flask'


# ============================================================
# 标签 CRUD 边界条件
# ============================================================

class TestTagCRUDEdgeCases:
    def test_update_nonexistent_tag(self, client):
        """编辑不存在的标签应返回 404"""
        resp = client.put('/tags/99999', json={'name': 'new_name'})
        assert resp.status_code == 404

    def test_delete_nonexistent_tag(self, client):
        """删除不存在的标签应返回 404"""
        resp = client.delete('/tags/99999')
        assert resp.status_code == 404

    def test_update_tag_to_duplicate_name(self, client):
        """更新标签名称为已存在的名称应失败"""
        client.post('/tags', json={'name': 'Python'})
        t2 = client.post('/tags', json={'name': 'Flask'}).json['data']
        resp = client.put(f'/tags/{t2["id"]}', json={'name': 'Python'})
        assert resp.status_code in (400, 409)

    def test_create_tag_with_empty_name(self, client):
        """创建标签时 name 为空字符串应失败"""
        resp = client.post('/tags', json={'name': ''})
        assert resp.status_code == 400


# ============================================================
# 文章标签绑定边界条件
# ============================================================

class TestArticleTagBindingEdgeCases:
    def test_bind_nonexistent_tag(self, client, sample_article):
        """绑定不存在的 tag_id 应失败"""
        resp = client.post(f'/articles/{sample_article}/tags',
                          json={'tag_ids': [99999]})
        assert resp.status_code in (400, 404)

    def test_bind_to_nonexistent_article(self, client):
        """为不存在的文章绑定标签应失败"""
        t = client.post('/tags', json={'name': 'Test'}).json['data']
        resp = client.post('/articles/99999/tags', json={'tag_ids': [t['id']]})
        assert resp.status_code == 404

    def test_rebind_same_tags_idempotent(self, client, sample_article):
        """重复绑定相同标签应是幂等的"""
        t = client.post('/tags', json={'name': 'Python'}).json['data']
        client.post(f'/articles/{sample_article}/tags', json={'tag_ids': [t['id']]})
        resp = client.post(f'/articles/{sample_article}/tags', json={'tag_ids': [t['id']]})
        assert resp.status_code == 200

        # 应仍然只有 1 个标签
        tags = client.get(f'/articles/{sample_article}/tags').json['data']
        assert len(tags) == 1

    def test_delete_tag_cleans_all_bindings(self, client):
        """删除标签应清除所有文章与该标签的关联"""
        a1 = client.post('/articles', json={'title': 'A1', 'body': 'B1'}).json['data']
        a2 = client.post('/articles', json={'title': 'A2', 'body': 'B2'}).json['data']
        t = client.post('/tags', json={'name': 'shared'}).json['data']

        client.post(f'/articles/{a1["id"]}/tags', json={'tag_ids': [t['id']]})
        client.post(f'/articles/{a2["id"]}/tags', json={'tag_ids': [t['id']]})

        # 删除标签
        client.delete(f'/tags/{t["id"]}')

        # 两篇文章的标签列表都应为空
        assert len(client.get(f'/articles/{a1["id"]}/tags').json['data']) == 0
        assert len(client.get(f'/articles/{a2["id"]}/tags').json['data']) == 0
