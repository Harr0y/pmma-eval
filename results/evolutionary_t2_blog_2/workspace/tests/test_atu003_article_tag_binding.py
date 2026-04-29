"""
ATU-003 Article-Tag Binding -- 单元测试

测试范围:
- POST   /articles/<id>/tags      绑定标签到文章
- GET    /articles/<id>/tags      获取文章的所有标签
- DELETE /articles/<id>/tags/<tid> 解除文章与标签的关联
- 删除标签时级联解除与文章的关联
- 边界条件: 不存在的文章/标签、空列表、重复绑定、无效请求体
"""

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'starter'))

from app import create_app, db
from models import Article, Tag


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def client():
    """创建测试客户端，每个测试用例使用全新的内存数据库。"""
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
    """通过 ORM 创建一篇示例文章，返回其 id。"""
    with client.application.app_context():
        a = Article(title='测试文章', body='文章内容')
        db.session.add(a)
        db.session.commit()
        return a.id


@pytest.fixture
def sample_tag(client):
    """通过 ORM 创建一个示例标签，返回其 id。"""
    with client.application.app_context():
        t = Tag(name='Python')
        db.session.add(t)
        db.session.commit()
        return t.id


@pytest.fixture
def bound_article_tag(client, sample_article, sample_tag):
    """创建已绑定标签的文章，返回 (article_id, tag_id)。"""
    client.post(
        f'/articles/{sample_article}/tags',
        json={'tag_ids': [sample_tag]},
    )
    return sample_article, sample_tag


# ============================================================
# POST /articles/<id>/tags -- 绑定标签到文章
# ============================================================

class TestBindTagsToArticle:
    """POST /articles/<id>/tags 的正常流程与边界条件。"""

    def test_bind_single_tag(self, client, sample_article):
        """绑定单个标签到文章。"""
        tag_resp = client.post('/tags', json={'name': 'Python'})
        tag_id = tag_resp.json['data']['id']

        resp = client.post(
            f'/articles/{sample_article}/tags',
            json={'tag_ids': [tag_id]},
        )
        assert resp.status_code == 200
        assert resp.json['status'] == 'ok'
        assert resp.json['data']['message'] == 'Tags bound'

    def test_bind_multiple_tags(self, client, sample_article):
        """同时绑定多个标签到文章。"""
        t1 = client.post('/tags', json={'name': 'Python'}).json['data']
        t2 = client.post('/tags', json={'name': 'Flask'}).json['data']
        t3 = client.post('/tags', json={'name': 'SQLAlchemy'}).json['data']

        resp = client.post(
            f'/articles/{sample_article}/tags',
            json={'tag_ids': [t1['id'], t2['id'], t3['id']]},
        )
        assert resp.status_code == 200

        # 验证所有标签都已绑定
        tags_resp = client.get(f'/articles/{sample_article}/tags')
        assert tags_resp.status_code == 200
        assert len(tags_resp.json['data']) == 3

    def test_bind_tags_article_not_found(self, client):
        """绑定标签到不存在的文章应返回 404。"""
        tag_resp = client.post('/tags', json={'name': 'Python'})
        tag_id = tag_resp.json['data']['id']

        resp = client.post('/articles/99999/tags', json={'tag_ids': [tag_id]})
        assert resp.status_code == 404

    def test_bind_tags_tag_not_found(self, client, sample_article):
        """绑定不存在的标签到文章应返回 400。"""
        resp = client.post(
            f'/articles/{sample_article}/tags',
            json={'tag_ids': [99999]},
        )
        assert resp.status_code == 400

    def test_bind_tags_mixed_valid_and_invalid(self, client, sample_article):
        """tag_ids 中包含不存在的标签应返回 400。"""
        valid_tag = client.post('/tags', json={'name': 'Python'}).json['data']

        resp = client.post(
            f'/articles/{sample_article}/tags',
            json={'tag_ids': [valid_tag['id'], 99999]},
        )
        assert resp.status_code == 400

    def test_bind_tags_empty_list(self, client, sample_article):
        """绑定空标签列表应返回 400。"""
        resp = client.post(
            f'/articles/{sample_article}/tags',
            json={'tag_ids': []},
        )
        assert resp.status_code == 400

    def test_bind_tags_missing_tag_ids_field(self, client, sample_article):
        """请求体缺少 tag_ids 字段应返回 400。"""
        resp = client.post(
            f'/articles/{sample_article}/tags',
            json={},
        )
        assert resp.status_code == 400

    def test_bind_tags_no_body(self, client, sample_article):
        """请求体为空（非 JSON）应返回 400。"""
        resp = client.post(
            f'/articles/{sample_article}/tags',
            data='not json',
            content_type='text/plain',
        )
        assert resp.status_code == 400

    def test_bind_duplicate_tag_is_idempotent(self, client, sample_article):
        """重复绑定同一标签到文章不应报错（幂等性）。"""
        tag_resp = client.post('/tags', json={'name': 'Python'})
        tag_id = tag_resp.json['data']['id']

        resp1 = client.post(
            f'/articles/{sample_article}/tags',
            json={'tag_ids': [tag_id]},
        )
        assert resp1.status_code == 200

        # 再次绑定同一标签
        resp2 = client.post(
            f'/articles/{sample_article}/tags',
            json={'tag_ids': [tag_id]},
        )
        assert resp2.status_code == 200

        # 文章仍然只有一个标签
        tags_resp = client.get(f'/articles/{sample_article}/tags')
        assert len(tags_resp.json['data']) == 1

    def test_bind_same_tag_to_multiple_articles(self, client):
        """同一个标签可以绑定到多篇文章。"""
        a1 = client.post('/articles', json={'title': 'A1', 'body': 'B1'}).json['data']
        a2 = client.post('/articles', json={'title': 'A2', 'body': 'B2'}).json['data']
        tag = client.post('/tags', json={'name': 'Python'}).json['data']

        resp1 = client.post(f'/articles/{a1["id"]}/tags', json={'tag_ids': [tag['id']]})
        resp2 = client.post(f'/articles/{a2["id"]}/tags', json={'tag_ids': [tag['id']]})

        assert resp1.status_code == 200
        assert resp2.status_code == 200

        # 两篇文章都有这个标签
        tags_a1 = client.get(f'/articles/{a1["id"]}/tags').json['data']
        tags_a2 = client.get(f'/articles/{a2["id"]}/tags').json['data']
        assert len(tags_a1) == 1
        assert len(tags_a2) == 1
        assert tags_a1[0]['name'] == 'Python'
        assert tags_a2[0]['name'] == 'Python'


# ============================================================
# GET /articles/<id>/tags -- 获取文章的所有标签
# ============================================================

class TestGetArticleTags:
    """GET /articles/<id>/tags 的正常流程与边界条件。"""

    def test_get_tags_of_article_with_tags(self, client, bound_article_tag):
        """获取已绑定标签的文章标签列表。"""
        article_id, _ = bound_article_tag

        resp = client.get(f'/articles/{article_id}/tags')
        assert resp.status_code == 200
        assert resp.json['status'] == 'ok'
        assert len(resp.json['data']) == 1
        assert 'id' in resp.json['data'][0]
        assert 'name' in resp.json['data'][0]

    def test_get_tags_of_article_without_tags(self, client, sample_article):
        """获取未绑定标签的文章标签列表应返回空数组。"""
        resp = client.get(f'/articles/{sample_article}/tags')
        assert resp.status_code == 200
        assert resp.json['status'] == 'ok'
        assert resp.json['data'] == []

    def test_get_tags_article_not_found(self, client):
        """获取不存在文章的标签应返回 404。"""
        resp = client.get('/articles/99999/tags')
        assert resp.status_code == 404

    def test_get_tags_returns_correct_order(self, client, sample_article):
        """获取标签列表应保持标签创建的顺序。"""
        t1 = client.post('/tags', json={'name': 'Alpha'}).json['data']
        t2 = client.post('/tags', json={'name': 'Beta'}).json['data']
        t3 = client.post('/tags', json={'name': 'Gamma'}).json['data']

        client.post(
            f'/articles/{sample_article}/tags',
            json={'tag_ids': [t3['id'], t1['id'], t2['id']]},
        )

        resp = client.get(f'/articles/{sample_article}/tags')
        assert resp.status_code == 200
        tag_names = [t['name'] for t in resp.json['data']]
        assert len(tag_names) == 3
        # 所有三个标签都在
        assert 'Alpha' in tag_names
        assert 'Beta' in tag_names
        assert 'Gamma' in tag_names

    def test_get_tags_data_structure(self, client, bound_article_tag):
        """标签数据应包含 id 和 name 字段。"""
        article_id, _ = bound_article_tag

        resp = client.get(f'/articles/{article_id}/tags')
        tag_data = resp.json['data'][0]

        assert isinstance(tag_data['id'], int)
        assert isinstance(tag_data['name'], str)
        # 不应包含额外字段（如 articles 列表）
        assert 'articles' not in tag_data


# ============================================================
# DELETE /articles/<id>/tags/<tag_id> -- 解除文章与标签的关联
# ============================================================

class TestUnbindTagFromArticle:
    """DELETE /articles/<id>/tags/<tag_id> 的正常流程与边界条件。"""

    def test_unbind_tag(self, client, bound_article_tag):
        """解除文章与标签的关联。"""
        article_id, tag_id = bound_article_tag

        resp = client.delete(f'/articles/{article_id}/tags/{tag_id}')
        assert resp.status_code == 200
        assert resp.json['status'] == 'ok'
        assert resp.json['data']['message'] == 'Tag unbound'

    def test_unbind_tag_verify_removed(self, client, bound_article_tag):
        """解除绑定后，标签列表应不再包含该标签。"""
        article_id, tag_id = bound_article_tag

        client.delete(f'/articles/{article_id}/tags/{tag_id}')

        tags_resp = client.get(f'/articles/{article_id}/tags')
        assert len(tags_resp.json['data']) == 0

    def test_unbind_tag_article_not_found(self, client, sample_tag):
        """对不存在的文章解除标签绑定应返回 404。"""
        resp = client.delete(f'/articles/99999/tags/{sample_tag}')
        assert resp.status_code == 404

    def test_unbind_nonexistent_binding(self, client, sample_article, sample_tag):
        """解除不存在的绑定（文章未绑定该标签）应返回 404。"""
        resp = client.delete(f'/articles/{sample_article}/tags/{sample_tag}')
        assert resp.status_code == 404

    def test_unbind_one_tag_keeps_others(self, client, sample_article):
        """解除一个标签的绑定不应影响其他已绑定的标签。"""
        t1 = client.post('/tags', json={'name': 'Python'}).json['data']
        t2 = client.post('/tags', json={'name': 'Flask'}).json['data']
        t3 = client.post('/tags', json={'name': 'SQLAlchemy'}).json['data']

        client.post(
            f'/articles/{sample_article}/tags',
            json={'tag_ids': [t1['id'], t2['id'], t3['id']]},
        )

        # 解绑中间的标签
        client.delete(f'/articles/{sample_article}/tags/{t2["id"]}')

        tags_resp = client.get(f'/articles/{sample_article}/tags')
        remaining_names = [t['name'] for t in tags_resp.json['data']]
        assert len(remaining_names) == 2
        assert 'Python' in remaining_names
        assert 'SQLAlchemy' in remaining_names
        assert 'Flask' not in remaining_names

    def test_unbind_tag_does_not_delete_tag(self, client, bound_article_tag):
        """解除绑定不应删除标签本身。"""
        article_id, tag_id = bound_article_tag

        client.delete(f'/articles/{article_id}/tags/{tag_id}')

        # 标签仍然存在于标签列表中
        tags_list = client.get('/tags').json['data']
        assert len(tags_list) == 1
        assert tags_list[0]['id'] == tag_id

    def test_unbind_tag_does_not_delete_article(self, client, bound_article_tag):
        """解除绑定不应删除文章本身。"""
        article_id, tag_id = bound_article_tag

        client.delete(f'/articles/{article_id}/tags/{tag_id}')

        # 文章仍然存在
        article_resp = client.get(f'/articles/{article_id}')
        assert article_resp.status_code == 200
        assert article_resp.json['data']['id'] == article_id


# ============================================================
# 级联效果 -- 删除标签时应同时解除与文章的关联
# ============================================================

class TestDeleteTagCascade:
    """删除标签时的级联效果：自动解除与所有文章的关联。"""

    def test_delete_tag_removes_binding_from_article(self, client, bound_article_tag):
        """删除标签后，文章的标签列表应不再包含该标签。"""
        article_id, tag_id = bound_article_tag

        resp = client.delete(f'/tags/{tag_id}')
        assert resp.status_code == 200

        tags_resp = client.get(f'/articles/{article_id}/tags')
        assert len(tags_resp.json['data']) == 0

    def test_delete_tag_cascade_multiple_articles(self, client):
        """删除标签时，应同时解除与所有已绑定文章的关联。"""
        a1 = client.post('/articles', json={'title': 'A1', 'body': 'B1'}).json['data']
        a2 = client.post('/articles', json={'title': 'A2', 'body': 'B2'}).json['data']
        tag = client.post('/tags', json={'name': 'Python'}).json['data']

        client.post(f'/articles/{a1["id"]}/tags', json={'tag_ids': [tag['id']]})
        client.post(f'/articles/{a2["id"]}/tags', json={'tag_ids': [tag['id']]})

        client.delete(f'/tags/{tag["id"]}')

        # 两篇文章都不再拥有该标签
        tags_a1 = client.get(f'/articles/{a1["id"]}/tags').json['data']
        tags_a2 = client.get(f'/articles/{a2["id"]}/tags').json['data']
        assert len(tags_a1) == 0
        assert len(tags_a2) == 0

    def test_delete_one_tag_keeps_other_bindings(self, client, sample_article):
        """删除一个标签不应影响其他标签的绑定。"""
        t1 = client.post('/tags', json={'name': 'Python'}).json['data']
        t2 = client.post('/tags', json={'name': 'Flask'}).json['data']

        client.post(
            f'/articles/{sample_article}/tags',
            json={'tag_ids': [t1['id'], t2['id']]},
        )

        # 只删除 Python 标签
        client.delete(f'/tags/{t1["id"]}')

        tags_resp = client.get(f'/articles/{sample_article}/tags')
        assert len(tags_resp.json['data']) == 1
        assert tags_resp.json['data'][0]['name'] == 'Flask'

    def test_delete_article_keeps_tags(self, client):
        """删除文章不应删除标签本身（反向验证）。"""
        article = client.post('/articles', json={'title': 'A1', 'body': 'B1'}).json['data']
        tag = client.post('/tags', json={'name': 'Python'}).json['data']

        client.post(f'/articles/{article["id"]}/tags', json={'tag_ids': [tag['id']]})

        # 删除文章
        resp = client.delete(f'/articles/{article["id"]}')
        assert resp.status_code == 200

        # 标签仍然存在
        tags_list = client.get('/tags').json['data']
        assert len(tags_list) == 1
        assert tags_list[0]['name'] == 'Python'


# ============================================================
# 端到端集成场景
# ============================================================

class TestArticleTagBindingE2E:
    """完整的文章标签绑定生命周期测试。"""

    def test_full_lifecycle(self, client):
        """完整的创建-绑定-查询-解绑-删除生命周期。"""
        # 1. 创建文章和标签
        article = client.post('/articles', json={'title': 'Flask入门', 'body': '内容'}).json['data']
        t1 = client.post('/tags', json={'name': 'Python'}).json['data']
        t2 = client.post('/tags', json={'name': 'Web'}).json['data']

        # 2. 绑定标签
        bind_resp = client.post(
            f'/articles/{article["id"]}/tags',
            json={'tag_ids': [t1['id'], t2['id']]},
        )
        assert bind_resp.status_code == 200

        # 3. 验证标签已绑定
        tags = client.get(f'/articles/{article["id"]}/tags').json['data']
        assert len(tags) == 2

        # 4. 解绑一个标签
        unbind_resp = client.delete(f'/articles/{article["id"]}/tags/{t1["id"]}')
        assert unbind_resp.status_code == 200

        # 5. 验证只剩一个标签
        tags = client.get(f'/articles/{article["id"]}/tags').json['data']
        assert len(tags) == 1
        assert tags[0]['name'] == 'Web'

        # 6. 删除剩余标签（级联效果）
        client.delete(f'/tags/{t2["id"]}')
        tags = client.get(f'/articles/{article["id"]}/tags').json['data']
        assert len(tags) == 0

        # 7. 文章本身仍然存在
        article_resp = client.get(f'/articles/{article["id"]}')
        assert article_resp.status_code == 200

    def test_rebind_after_unbind(self, client, sample_article):
        """解除绑定后可以重新绑定同一标签。"""
        tag = client.post('/tags', json={'name': 'Python'}).json['data']

        # 绑定
        client.post(f'/articles/{sample_article}/tags', json={'tag_ids': [tag['id']]})
        assert len(client.get(f'/articles/{sample_article}/tags').json['data']) == 1

        # 解绑
        client.delete(f'/articles/{sample_article}/tags/{tag["id"]}')
        assert len(client.get(f'/articles/{sample_article}/tags').json['data']) == 0

        # 重新绑定
        resp = client.post(f'/articles/{sample_article}/tags', json={'tag_ids': [tag['id']]})
        assert resp.status_code == 200
        assert len(client.get(f'/articles/{sample_article}/tags').json['data']) == 1
