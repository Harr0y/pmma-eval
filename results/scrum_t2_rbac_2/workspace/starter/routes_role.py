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
from models import Role, Permission, User, user_roles, role_permissions
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


def _resolve_permissions(perm_codes):
    """Given a list of permission code strings, find or create Permission records."""
    perms = []
    for code in perm_codes:
        perm = Permission.query.filter_by(code=code).first()
        if perm is None:
            perm = Permission(code=code)
            db.session.add(perm)
        perms.append(perm)
    return perms


def _would_create_cycle(role_id, new_parent_id):
    """Check if setting role's parent to new_parent_id would create a cycle.

    Walks up the parent chain from new_parent_id. If we reach role_id,
    it means role would be its own ancestor -> cycle.
    """
    current = new_parent_id
    visited = set()
    while current is not None:
        if current == role_id:
            return True
        if current in visited:
            return True
        visited.add(current)
        parent_role = Role.query.get(current)
        if parent_role is None:
            break
        current = parent_role.parent_role_id
    return False


@role_bp.route('/roles', methods=['POST'])
@check_permission('role.manage')
def create_role():
    """Create a new role in the current user's tenant."""
    data = request.get_json(silent=True)
    if not data or 'name' not in data:
        return jsonify({'status': 'error', 'message': 'Role name is required'}), 400

    name = data['name']
    permissions = data.get('permissions', [])
    parent_role_id = data.get('parent_role_id')

    user = g.current_user
    tenant_id = user.tenant_id

    # Check duplicate name within same tenant
    existing = Role.query.filter_by(tenant_id=tenant_id, name=name).first()
    if existing:
        return jsonify({'status': 'error', 'message': 'Role name already exists in this tenant'}), 409

    # Validate parent_role_id belongs to same tenant
    if parent_role_id is not None:
        parent_role = Role.query.get(parent_role_id)
        if parent_role is None or parent_role.tenant_id != tenant_id:
            return jsonify({'status': 'error', 'message': 'Invalid parent role'}), 400

    role = Role(tenant_id=tenant_id, name=name, parent_role_id=parent_role_id)
    db.session.add(role)
    db.session.flush()  # get role.id

    # Set permissions
    if permissions:
        perms = _resolve_permissions(permissions)
        role.permissions = perms

    db.session.commit()

    return jsonify({'status': 'ok', 'data': _role_to_dict(role)}), 201


@role_bp.route('/roles', methods=['GET'])
@check_permission('role.manage')
def list_roles():
    """List all roles for the current user's tenant."""
    user = g.current_user
    tenant_id = user.tenant_id

    roles = Role.query.filter_by(tenant_id=tenant_id).all()
    return jsonify({'status': 'ok', 'data': [_role_to_dict(r) for r in roles]}), 200


@role_bp.route('/roles/<int:role_id>/permissions', methods=['PUT'])
@check_permission('role.manage')
def update_role_permissions(role_id):
    """Replace a role's permission set and optionally update parent."""
    role = Role.query.get(role_id)
    if role is None:
        return jsonify({'status': 'error', 'message': 'Role not found'}), 404

    user = g.current_user
    tenant_id = user.tenant_id

    # Ensure role belongs to current tenant
    if role.tenant_id != tenant_id:
        return jsonify({'status': 'error', 'message': 'Role not found'}), 404

    data = request.get_json(silent=True)
    if not data:
        return jsonify({'status': 'error', 'message': 'Request body required'}), 400

    permissions = data.get('permissions', [])
    new_parent_id = data.get('parent_role_id')

    # Validate parent_role_id
    if new_parent_id is not None:
        if new_parent_id == role_id:
            return jsonify({'status': 'error', 'message': 'Cannot set self as parent'}), 400
        parent_role = Role.query.get(new_parent_id)
        if parent_role is None or parent_role.tenant_id != tenant_id:
            return jsonify({'status': 'error', 'message': 'Invalid parent role'}), 400

        # Cycle detection: walk up from new_parent_id, must not reach role_id
        if _would_create_cycle(role_id, new_parent_id):
            return jsonify({'status': 'error', 'message': 'Inheritance cycle detected'}), 400

    # Update parent
    role.parent_role_id = new_parent_id

    # Replace permissions
    role.permissions = _resolve_permissions(permissions) if permissions else []

    db.session.commit()

    return jsonify({'status': 'ok', 'data': _role_to_dict(role)}), 200


@role_bp.route('/users/<int:user_id>/roles', methods=['POST'])
@check_permission('role.manage')
def assign_role_to_user(user_id):
    """Assign a role to a user. Both must belong to the same tenant."""
    user = g.current_user
    tenant_id = user.tenant_id

    target_user = User.query.get(user_id)
    if target_user is None:
        return jsonify({'status': 'error', 'message': 'User not found'}), 404

    data = request.get_json(silent=True)
    if not data or 'role_id' not in data:
        return jsonify({'status': 'error', 'message': 'role_id is required'}), 400

    role_id = data['role_id']
    role = Role.query.get(role_id)
    if role is None:
        return jsonify({'status': 'error', 'message': 'Role not found'}), 404

    # Cross-tenant check: both user and role must belong to same tenant
    if target_user.tenant_id != tenant_id or role.tenant_id != tenant_id:
        return jsonify({'status': 'error', 'message': 'User and role must belong to same tenant'}), 403

    # Add role to user (if not already assigned)
    if role not in target_user.roles:
        target_user.roles.append(role)
        db.session.commit()

    return jsonify({'status': 'ok', 'data': {'user_id': user_id, 'role_id': role_id}}), 200


@role_bp.route('/users/<int:user_id>/roles/<int:role_id>', methods=['DELETE'])
@check_permission('role.manage')
def remove_role_from_user(user_id, role_id):
    """Remove a role from a user. Idempotent — no error if not assigned."""
    user = g.current_user
    tenant_id = user.tenant_id

    target_user = User.query.get(user_id)
    if target_user is None:
        return jsonify({'status': 'error', 'message': 'User not found'}), 404

    role = Role.query.get(role_id)
    if role is not None and role in target_user.roles:
        target_user.roles.remove(role)
        db.session.commit()

    return jsonify({'status': 'ok', 'data': {'user_id': user_id, 'role_id': role_id}}), 200
