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
from app import db
from middleware import check_permission

role_bp = Blueprint('role_bp', __name__)


def _role_to_dict(role):
    """Serialize a role to dict with permission codes."""
    return {
        'id': role.id,
        'name': role.name,
        'parent_role_id': role.parent_role_id,
        'permissions': [p.code for p in role.permissions],
    }


def _detect_cycle(role_id, parent_role_id):
    """Walk up the parent chain from parent_role_id. If we reach role_id, it's a cycle."""
    visited = set()
    current = parent_role_id
    while current is not None:
        if current == role_id:
            return True
        if current in visited:
            return True  # already-seen cycle in the chain itself
        visited.add(current)
        parent = Role.query.get(current)
        if parent is None:
            break
        current = parent.parent_role_id
    return False


def _set_role_permissions(role, perm_codes):
    """Replace the role's permission set with the given list of permission codes."""
    role.permissions = []
    db.session.flush()
    for code in perm_codes:
        perm = Permission.query.filter_by(code=code).first()
        if perm:
            role.permissions.append(perm)


@role_bp.route('/roles', methods=['POST'])
@check_permission('role.manage')
def create_role():
    data = request.get_json(silent=True) or {}
    name = data.get('name')

    if not name:
        return jsonify({'status': 'error', 'message': 'Name is required'}), 400

    user = g.current_user
    tenant_id = user.tenant_id

    if Role.query.filter_by(tenant_id=tenant_id, name=name).first():
        return jsonify({'status': 'error', 'message': 'Role name already exists'}), 409

    parent_role_id = data.get('parent_role_id')
    if parent_role_id is not None:
        parent = Role.query.get(parent_role_id)
        if not parent or parent.tenant_id != tenant_id:
            return jsonify({'status': 'error', 'message': 'Invalid parent role'}), 400

    role = Role(tenant_id=tenant_id, name=name, parent_role_id=parent_role_id)
    db.session.add(role)
    db.session.flush()

    _set_role_permissions(role, data.get('permissions', []))
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
    role = Role.query.get(role_id)
    if not role:
        return jsonify({'status': 'error', 'message': 'Role not found'}), 404

    data = request.get_json(silent=True) or {}
    user = g.current_user
    tenant_id = user.tenant_id

    if role.tenant_id != tenant_id:
        return jsonify({'status': 'error', 'message': 'Role not found'}), 404

    new_parent_id = data.get('parent_role_id')
    if new_parent_id is not None:
        parent = Role.query.get(new_parent_id)
        if not parent or parent.tenant_id != tenant_id:
            return jsonify({'status': 'error', 'message': 'Invalid parent role'}), 400
        if _detect_cycle(role_id, new_parent_id):
            return jsonify({'status': 'error', 'message': 'Inheritance cycle detected'}), 400

    role.parent_role_id = new_parent_id
    _set_role_permissions(role, data.get('permissions', []))
    db.session.commit()

    return jsonify({'status': 'ok', 'data': _role_to_dict(role)})


@role_bp.route('/users/<int:user_id>/roles', methods=['POST'])
@check_permission('role.manage')
def assign_role(user_id):
    target_user = User.query.get(user_id)
    if not target_user:
        return jsonify({'status': 'error', 'message': 'User not found'}), 404

    data = request.get_json(silent=True) or {}
    role_id = data.get('role_id')

    role = Role.query.get(role_id)
    if not role:
        return jsonify({'status': 'error', 'message': 'Role not found'}), 404

    current_user = g.current_user
    if target_user.tenant_id != current_user.tenant_id or role.tenant_id != current_user.tenant_id:
        return jsonify({'status': 'error', 'message': 'Cross-tenant operation forbidden'}), 403

    # Check if already assigned
    existing = db.session.query(user_roles).filter_by(
        user_id=user_id, role_id=role_id
    ).first()
    if not existing:
        db.session.execute(user_roles.insert().values(user_id=user_id, role_id=role_id))
        db.session.commit()

    return jsonify({'status': 'ok', 'data': {'user_id': user_id, 'role_id': role_id}})


@role_bp.route('/users/<int:user_id>/roles/<int:role_id>', methods=['DELETE'])
@check_permission('role.manage')
def remove_role(user_id, role_id):
    target_user = User.query.get(user_id)
    if not target_user:
        return jsonify({'status': 'error', 'message': 'User not found'}), 404

    db.session.execute(
        user_roles.delete().where(
            user_roles.c.user_id == user_id,
            user_roles.c.role_id == role_id,
        )
    )
    db.session.commit()

    return jsonify({'status': 'ok', 'data': {'user_id': user_id, 'role_id': role_id}})
