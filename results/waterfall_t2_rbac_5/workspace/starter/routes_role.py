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
from models import Role, Permission, User
from middleware import check_permission
from app import db

role_bp = Blueprint('role_bp', __name__)


def _serialize_role(role):
    """Serialize a role to a dict with permission codes."""
    return {
        'id': role.id,
        'name': role.name,
        'parent_role_id': role.parent_role_id,
        'permissions': [p.code for p in role.permissions],
    }


def _would_create_cycle(role_id, new_parent_id):
    """Check if setting role_id's parent to new_parent_id would create a cycle.

    Algorithm (design.md section 3.1):
    Walk up the chain from new_parent_id via parent_role_id.
    If we encounter role_id, a cycle would form.
    """
    if new_parent_id is None:
        return False

    visited = set()
    current = new_parent_id
    while current is not None:
        if current == role_id:
            return True
        if current in visited:
            # Existing cycle in DB (not introduced by this change), skip
            return False
        visited.add(current)
        current_role = Role.query.get(current)
        if current_role is None:
            return False
        current = current_role.parent_role_id
    return False


@role_bp.route('/roles', methods=['POST'])
@check_permission('role.manage')
def create_role():
    """Create a new role in the current tenant."""
    data = request.get_json(silent=True) or {}
    name = data.get('name')

    if not name:
        return jsonify({'status': 'error', 'message': 'Missing required field: name'}), 400

    tenant_id = g.current_user.tenant_id

    # Check duplicate role name within same tenant
    existing = Role.query.filter_by(tenant_id=tenant_id, name=name).first()
    if existing:
        return jsonify({'status': 'error', 'message': 'Role name already exists in this tenant'}), 409

    permissions = data.get('permissions', [])
    parent_role_id = data.get('parent_role_id', None)

    # Validate parent role if provided
    if parent_role_id is not None:
        parent = Role.query.get(parent_role_id)
        if parent is None or parent.tenant_id != tenant_id:
            return jsonify({'status': 'error', 'message': 'Parent role not found or not in same tenant'}), 400

    role = Role(tenant_id=tenant_id, name=name, parent_role_id=parent_role_id)

    # Cycle detection: when creating a new role, role.id is None until flush,
    # so we need to flush first to get the id, then check cycle.
    db.session.add(role)
    db.session.flush()

    if parent_role_id is not None:
        if _would_create_cycle(role.id, parent_role_id):
            db.session.rollback()
            return jsonify({'status': 'error', 'message': 'Inheritance cycle detected'}), 400

    # Associate permissions by code
    if permissions:
        perms = Permission.query.filter(Permission.code.in_(permissions)).all()
        role.permissions.extend(perms)

    db.session.commit()
    return jsonify({'status': 'ok', 'data': _serialize_role(role)}), 201


@role_bp.route('/roles', methods=['GET'])
@check_permission('role.manage')
def list_roles():
    """List all roles for the current tenant."""
    tenant_id = g.current_user.tenant_id
    roles = Role.query.filter_by(tenant_id=tenant_id).all()
    return jsonify({'status': 'ok', 'data': [_serialize_role(r) for r in roles]}), 200


@role_bp.route('/roles/<int:role_id>/permissions', methods=['PUT'])
@check_permission('role.manage')
def update_role_permissions(role_id):
    """Update role permissions and/or parent role (partial update)."""
    role = Role.query.get(role_id)
    if role is None:
        return jsonify({'status': 'error', 'message': 'Role not found'}), 404

    data = request.get_json(silent=True) or {}
    tenant_id = g.current_user.tenant_id

    # Handle parent_role_id update
    if 'parent_role_id' in data:
        new_parent_id = data['parent_role_id']
        if new_parent_id is not None:
            parent = Role.query.get(new_parent_id)
            if parent is None or parent.tenant_id != tenant_id:
                return jsonify({'status': 'error', 'message': 'Parent role not found or not in same tenant'}), 400
            if _would_create_cycle(role_id, new_parent_id):
                return jsonify({'status': 'error', 'message': 'Inheritance cycle detected'}), 400
        role.parent_role_id = new_parent_id

    # Handle permissions update
    if 'permissions' in data:
        role.permissions = []
        codes = data['permissions']
        if codes:
            perms = Permission.query.filter(Permission.code.in_(codes)).all()
            role.permissions.extend(perms)

    db.session.commit()
    return jsonify({'status': 'ok', 'data': _serialize_role(role)}), 200


@role_bp.route('/users/<int:user_id>/roles', methods=['POST'])
@check_permission('role.manage')
def assign_role_to_user(user_id):
    """Assign a role to a user. Both must belong to the current tenant."""
    target_user = User.query.get(user_id)
    if target_user is None:
        return jsonify({'status': 'error', 'message': 'User not found'}), 404

    data = request.get_json(silent=True) or {}
    role_id = data.get('role_id')

    if role_id is None:
        return jsonify({'status': 'error', 'message': 'Missing required field: role_id'}), 400

    role = Role.query.get(role_id)
    if role is None:
        return jsonify({'status': 'error', 'message': 'Role not found'}), 404

    tenant_id = g.current_user.tenant_id

    if target_user.tenant_id != tenant_id:
        return jsonify({'status': 'error', 'message': 'Target user is not in the same tenant'}), 403

    if role.tenant_id != tenant_id:
        return jsonify({'status': 'error', 'message': 'Role is not in the same tenant'}), 403

    if role not in target_user.roles:
        target_user.roles.append(role)

    db.session.commit()
    return jsonify({'status': 'ok', 'data': None}), 200


@role_bp.route('/users/<int:user_id>/roles/<int:role_id>', methods=['DELETE'])
@check_permission('role.manage')
def remove_role_from_user(user_id, role_id):
    """Remove a role from a user. Idempotent — no error if not assigned."""
    target_user = User.query.get(user_id)
    if target_user is None:
        return jsonify({'status': 'error', 'message': 'User not found'}), 404

    role = Role.query.get(role_id)
    if role is not None and role in target_user.roles:
        target_user.roles.remove(role)

    db.session.commit()
    return jsonify({'status': 'ok', 'data': None}), 200
