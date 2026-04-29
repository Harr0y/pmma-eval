"""
T2 RBAC System — Role Management Routes

Role CRUD, user-role assignment, permission management.
Register as a Flask Blueprint named 'role_bp'.
All operations require role.manage permission.

Requirements:
- POST /roles -> Create role
  Requires: role.manage
  Request: {"name": str, "parent_role_id": int|null, "permissions": [str, ...]}
  Response: {"status": "ok", "data": {"id": int, "name": str, "parent_role_id": int|null,
            "permissions": [str, ...]}}
  - Must check for duplicate role names within same tenant
  - parent_role_id must belong to same tenant
Errors: 400 if name missing or parent invalid, 409 if duplicate name

- GET /roles -> List roles for current tenant
  Requires: role.manage
  Response: {"status": "ok", "data": [...]}

- PUT /roles/<id>/permissions -> Update role permissions and/or parent
  Requires: role.manage
  Request: {"permissions": [str, ...], "parent_role_id": int|null}
  - Must detect inheritance cycles when setting parent_role_id
Errors: 404 if role not found, 400 if cycle detected or parent invalid

- POST /users/<id>/roles -> Assign role to user
  Requires: role.manage
  Request: {"role_id": int}
  - Both user and role must belong to same tenant
Errors: 404 if user or role not found

- DELETE /users/<id>/roles/<role_id> -> Remove role from user
  Requires: role.manage
  - Idempotent — no error if role not assigned
Errors: 404 if user not found

IMPORTANT: Role inheritance is handled by middleware._collect_role_permissions().
Roles are tenant-scoped. This module works with middleware.py and routes_document.py.
"""

from flask import Blueprint, request, jsonify, g
from models import Role, Permission, User, role_permissions, user_roles
from middleware import check_permission
from app import db

role_bp = Blueprint('role_bp', __name__)


def _serialize_role(role):
    """Serialize a role to JSON-serializable dict."""
    return {
        'id': role.id,
        'name': role.name,
        'parent_role_id': role.parent_role_id,
        'permissions': [p.code for p in role.permissions],
    }


def _has_cycle(role_id, parent_id):
    """Check if setting parent_id on role_id would create a cycle.
    Walk up the parent chain from parent_id; if we encounter role_id, it's a cycle."""
    visited = set()
    current = parent_id
    while current is not None:
        if current == role_id:
            return True
        if current in visited:
            break
        visited.add(current)
        role = Role.query.get(current)
        if role is None:
            break
        current = role.parent_role_id
    return False


@role_bp.route('/roles', methods=['POST'])
@check_permission('role.manage')
def create_role():
    data = request.get_json(silent=True) or {}
    name = data.get('name')
    if not name:
        return jsonify({'status': 'error', 'message': 'Name is required'}), 400

    tenant_id = g.current_user.tenant_id

    # Check duplicate name within same tenant
    existing = Role.query.filter_by(tenant_id=tenant_id, name=name).first()
    if existing:
        return jsonify({'status': 'error', 'message': 'Role name already exists'}), 409

    # Validate parent_role_id if provided
    parent_role_id = data.get('parent_role_id')
    if parent_role_id is not None:
        parent = Role.query.get(parent_role_id)
        if parent is None or parent.tenant_id != tenant_id:
            return jsonify({'status': 'error', 'message': 'Invalid parent role'}), 400

    role = Role(tenant_id=tenant_id, name=name, parent_role_id=parent_role_id)

    # Resolve permission codes to Permission objects
    perm_codes = data.get('permissions', [])
    if perm_codes:
        perms = Permission.query.filter(Permission.code.in_(perm_codes)).all()
        role.permissions = perms

    db.session.add(role)
    db.session.commit()

    return jsonify({'status': 'ok', 'data': _serialize_role(role)}), 201


@role_bp.route('/roles', methods=['GET'])
@check_permission('role.manage')
def list_roles():
    tenant_id = g.current_user.tenant_id
    roles = Role.query.filter_by(tenant_id=tenant_id).all()
    return jsonify({'status': 'ok', 'data': [_serialize_role(r) for r in roles]})


@role_bp.route('/roles/<int:role_id>/permissions', methods=['PUT'])
@check_permission('role.manage')
def update_role_permissions(role_id):
    role = Role.query.get(role_id)
    if role is None:
        return jsonify({'status': 'error', 'message': 'Role not found'}), 404

    tenant_id = g.current_user.tenant_id

    data = request.get_json(silent=True) or {}

    # Update parent_role_id if provided
    if 'parent_role_id' in data:
        parent_role_id = data['parent_role_id']
        if parent_role_id is not None:
            parent = Role.query.get(parent_role_id)
            if parent is None or parent.tenant_id != tenant_id:
                return jsonify({'status': 'error', 'message': 'Invalid parent role'}), 400
            # Cycle detection
            if _has_cycle(role_id, parent_role_id):
                return jsonify({'status': 'error', 'message': 'Inheritance cycle detected'}), 400
        role.parent_role_id = parent_role_id

    # Replace permissions if provided
    if 'permissions' in data:
        perm_codes = data['permissions']
        if perm_codes:
            perms = Permission.query.filter(Permission.code.in_(perm_codes)).all()
            role.permissions = perms
        else:
            role.permissions = []

    db.session.commit()
    return jsonify({'status': 'ok', 'data': _serialize_role(role)})


@role_bp.route('/users/<int:user_id>/roles', methods=['POST'])
@check_permission('role.manage')
def assign_role(user_id):
    user = User.query.get(user_id)
    if user is None:
        return jsonify({'status': 'error', 'message': 'User not found'}), 404

    data = request.get_json(silent=True) or {}
    role_id = data.get('role_id')
    if role_id is None:
        return jsonify({'status': 'error', 'message': 'role_id is required'}), 400

    role = Role.query.get(role_id)
    if role is None:
        return jsonify({'status': 'error', 'message': 'Role not found'}), 404

    # Cross-tenant check
    if user.tenant_id != role.tenant_id:
        return jsonify({'status': 'error', 'message': 'User and role must belong to same tenant'}), 403

    # Assign role (use raw insert to avoid duplicate errors)
    existing = db.session.execute(
        user_roles.select().where(
            user_roles.c.user_id == user_id,
            user_roles.c.role_id == role_id
        )
    ).fetchone()
    if not existing:
        db.session.execute(user_roles.insert().values(user_id=user_id, role_id=role_id))
        db.session.commit()

    return jsonify({'status': 'ok', 'data': {'user_id': user_id, 'role_id': role_id}})


@role_bp.route('/users/<int:user_id>/roles/<int:target_role_id>', methods=['DELETE'])
@check_permission('role.manage')
def remove_role(user_id, target_role_id):
    user = User.query.get(user_id)
    if user is None:
        return jsonify({'status': 'error', 'message': 'User not found'}), 404

    # Idempotent: just delete if exists, no error if not
    db.session.execute(
        user_roles.delete().where(
            user_roles.c.user_id == user_id,
            user_roles.c.role_id == target_role_id
        )
    )
    db.session.commit()

    return jsonify({'status': 'ok', 'data': {'user_id': user_id, 'role_id': target_role_id}})
