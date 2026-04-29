"""
T2 RBAC System — Document Routes

Document CRUD with RBAC enforcement.
Register as a Flask Blueprint named 'document_bp'.

Permission requirements:
- GET /documents → doc.read (own tenant only)
- GET /documents/<id> → doc.read + same tenant
- POST /documents → doc.write
- PUT /documents/<id> → doc.write + (owner OR doc.write.any)
- DELETE /documents/<id> → doc.delete

Requirements:
- GET /documents -> List documents for current user's tenant
  Requires: doc.read permission
  Response: {"status": "ok", "data": [{"id": int, "tenant_id": int, "owner_id": int,
            "title": str, "content": str}, ...]}

- POST /documents -> Create document
  Requires: doc.write permission
  Request: {"title": str, "content": str}
  Response: {"status": "ok", "data": {"id": int, "tenant_id": int, "owner_id": int,
            "title": str, "content": str}}
  - tenant_id from JWT, owner_id = current user

- GET /documents/<id> -> Get single document
  Requires: doc.read + same tenant
  Response: same as above
  Errors: 404 if not found or different tenant

- PUT /documents/<id> -> Update document
  Requires: doc.write + (owner OR doc.write.any permission) + same tenant
  Request: {"title": str, "content": str}
  Errors: 404 if not found, 403 if not owner and no doc.write.any

- DELETE /documents/<id> -> Delete document
  Requires: doc.delete permission + same tenant
  Errors: 404 if not found, 403 if no permission

IMPORTANT: Uses middleware.get_current_user() for JWT auth and
middleware.get_user_permissions() for permission checking.
Documents are tenant-scoped — users can only see/edit their own tenant's docs.
"""

from flask import Blueprint, request, jsonify

document_bp = Blueprint('document_bp', __name__)

# TODO: Implement all document routes with RBAC enforcement
