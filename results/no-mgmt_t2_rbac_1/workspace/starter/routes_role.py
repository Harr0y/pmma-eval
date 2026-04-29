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
from models import Role, Permission, User, user_roles
from middleware import check_permission
from app import db

role_bp = Blueprint('role_bp', __name__)


def _role_to_dict(role):
    return {
        'id': role.id,
        'name': role.name,
        'parent_role_id': role.parent_role_id,
        'permissions': [p.code for p in role.permissions],
    }


def _detect_cycle(role_id, target_parent_id):
    """Check if setting role's parent to target_parent_id would create a cycle."""
    visited = set()
    current = target_parent_id
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


def _resolve_permission_ids(perm_codes):
    """Convert permission code strings to Permission objects."""
    perms = []
    for code in perm_codes:
        perm = Permission.query.filter_by(code=code).first()
        if perm:
            perms.append(perm)
    return perms


@role_bp.route('/roles', methods=['POST'])
@check_permission('role.manage')
def create_role():
    user = g.current_user
    data = request.get_json(silent=True) or {}
    name = data.get('name')
    permissions = data.get('permissions', [])
    parent_role_id = data.get('parent_role_id')

    if not name:
        return jsonify({'status': 'error', 'message': 'Role name is required'}), 400

    # Check duplicate name within same tenant
    existing = Role.query.filter_by(tenant_id=user.tenant_id, name=name).first()
    if existing:
        return jsonify({'status': 'error', 'message': 'Role name already exists'}), 409

    # Validate parent_role_id
    if parent_role_id is not None:
        parent = Role.query.get(parent_role_id)
        if parent is None or parent.tenant_id != user.tenant_id:
            return jsonify({'status': 'error', 'message': 'Invalid parent role'}), 400

    role = Role(tenant_id=user.tenant_id, name=name,
                parent_role_id=parent_role_id)
    role.permissions = _resolve_permission_ids(permissions)

    db.session.add(role)
    db.session.commit()

    return jsonify({'status': 'ok', 'data': _role_to_dict(role)}), 201


@role_bp.route('/roles', methods=['GET'])
@check_permission('role.manage')
def list_roles():
    user = g.current_user
    roles = Role.query.filter_by(tenant_id=user.tenant_id).all()
    return jsonify({'status': 'ok', 'data': [_role_to_dict(r) for r in roles]})


@role_bp.route('/roles/<int:role_id>/permissions', methods=['PUT'])
@check_permission('role.manage')
def update_role_permissions(role_id):
    user = g.current_user
    data = request.get_json(silent=True) or {}
    permissions = data.get('permissions', [])
    parent_role_id = data.get('parent_role_id')

    role = Role.query.get(role_id)
    if role is None or role.tenant_id != user.tenant_id:
        return jsonify({'status': 'error', 'message': 'Role not found'}), 404

    # Update parent_role_id if provided
    if parent_role_id is not None:
        parent = Role.query.get(parent_role_id)
        if parent is None or parent.tenant_id != user.tenant_id:
            return jsonify({'status': 'error', 'message': 'Invalid parent role'}), 400
        # Cycle detection
        if _detect_cycle(role_id, parent_role_id):
            return jsonify({'status': 'error', 'message': 'Inheritance cycle detected'}), 400
        role.parent_role_id = parent_role_id
    elif 'parent_role_id' in data and data['parent_role_id'] is None:
        # Explicitly set to null
        role.parent_role_id = None

    # Replace permissions
    role.permissions = _resolve_permission_ids(permissions)
    db.session.commit()

    return jsonify({'status': 'ok', 'data': _role_to_dict(role)})


@role_bp.route('/users/<int:user_id>/roles', methods=['POST'])
@check_permission('role.manage')
def assign_role(user_id):
    current = g.current_user
    data = request.get_json(silent=True) or {}
    role_id = data.get('role_id')

    target_user = User.query.get(user_id)
    if target_user is None:
        return jsonify({'status': 'error', 'message': 'User not found'}), 404

    # Both user and role must belong to same tenant
    if target_user.tenant_id != current.tenant_id:
        return jsonify({'status': 'error', 'message': 'User not found'}), 404

    role = Role.query.get(role_id)
    if role is None or role.tenant_id != current.tenant_id:
        return jsonify({'status': 'error', 'message': 'Role not found'}), 404

    # Check if already assigned
    already = db.session.execute(
        user_roles.select().where(
            (user_roles.c.user_id == user_id) & (user_roles.c.role_id == role_id)
        )
    ).fetchone()

    if not already:
        db.session.execute(
            user_roles.insert().values(user_id=user_id, role_id=role_id)
        )
        db.session.commit()

    return jsonify({'status': 'ok', 'data': None})


@role_bp.route('/users/<int:user_id>/roles/<int:role_id>', methods=['DELETE'])
@check_permission('role.manage')
def remove_role(user_id, role_id):
    current = g.current_user

    target_user = User.query.get(user_id)
    if target_user is None:
        return jsonify({'status': 'error', 'message': 'User not found'}), 404

    # Idempotent — just try to delete, no error if not assigned
    db.session.execute(
        user_roles.delete().where(
            (user_roles.c.user_id == user_id) & (user_roles.c.role_id == role_id)
        )
    )
    db.session.commit()

    return jsonify({'status': 'ok', 'data': None})
