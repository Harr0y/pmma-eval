# T2-1：小型博客系统 — 文章标签管理 + 按标签筛选（多模块版本）

## 项目结构

```
starter/
  app.py              # Flask app 工厂 + DB 初始化（请勿修改）
  models.py           # 数据模型（Article, Tag, article_tags）—— 需要完善
  routes_article.py   # 文章路由 + 标签绑定 —— 需要实现
  routes_tag.py       # 标签 CRUD 路由 —— 需要实现
  requirements.txt    # 依赖
```

## 重要提示

这是一个**多模块项目**，代码分布在多个文件中。各模块之间有 import 依赖：
- `routes_article.py` 和 `routes_tag.py` 需要从 `models.py` 导入模型
- `app.py` 负责组装所有模块（请勿修改）

**请确保各模块之间的接口（模型字段名、关联表名）保持一致。**

## 功能要求

### 1. 数据模型（models.py）
- Article 模型：id, title, body
- Tag 模型：id, name（唯一、非空）
- article_tags 多对多关联表

### 2. 文章路由（routes_article.py）
使用 `article_bp = Blueprint('article_bp', __name__)`
- `GET /articles` → 列出所有文章（可选 `?tag=<name>` 或 `?tag_id=<id>` 筛选）
- `POST /articles` → 创建文章 `{"title": "...", "body": "..."}`
- `GET /articles/<id>` → 获取单篇文章
- `POST /articles/<id>/tags` → 绑定标签 `{"tag_ids": [1, 2]}`
- `GET /articles/<id>/tags` → 获取文章的所有标签
- `DELETE /articles/<id>/tags/<tag_id>` → 解除文章与标签的关联

### 3. 标签路由（routes_tag.py）
使用 `tag_bp = Blueprint('tag_bp', __name__)`
- `POST /tags` → 创建标签（name 必填，不可重复）
- `GET /tags` → 获取所有标签列表
- `PUT /tags/<id>` → 编辑标签名称
- `DELETE /tags/<id>` → 删除标签（同时解除与文章的关联）

### 接口返回格式

成功时：
```json
{"status": "ok", "data": ...}
```

错误时：
```json
{"status": "error", "message": "错误描述"}
```

## 验收标准

1. ✅ 所有上述 API 接口可正常调用
2. ✅ `tests/test_basic.py` 中的所有测试用例通过
3. ✅ 本文件（README.md）无需修改内容

## 测试

```bash
cd starter && pip install -r requirements.txt && cd .. && python -m pytest tests/ -v
```
