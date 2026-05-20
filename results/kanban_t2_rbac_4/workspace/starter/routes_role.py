"""
T2 RBAC System -- Role Management Routes

Role CRUD, user-role assignment, permission management.
Register as a Flask Blueprint named 'role_bp'.
All operations require role.manage permission.

Requirements:
- POST /roles -> Create role
- GET /roles -> List roles for current tenant
- PUT /roles/<id>/permissions -> Update role permissions and/or parent
- POST /users/<id>/roles -> Assign role to user
- DELETE /users/<id>/roles/<role_id> -> Remove role from user

IMPORTANT: Role inheritance is handled by middleware._collect_role_permissions().
Roles are tenant-scoped. This module works with middleware.py and routes_document.py.
"""

from flask import Blueprint, request, jsonify, g
from models import Role, Permission, User, role_permissions, user_roles
from middleware import check_permission
from app import db

role_bp = Blueprint('role_bp', __name__)


def _role_to_dict(role):
    """Serialize a role to API response format."""
    return {
        'id': role.id,
        'name': role.name,
        'parent_role_id': role.parent_role_id,
        'permissions': [p.code for p in role.permissions],
    }


def _has_cycle(role_id, parent_id):
    """Check if setting role's parent to parent_id would create a cycle."""
    visited = set()
    current = parent_id
    while current is not None:
        if current == role_id:
            return True
        if current in visited:
            return True
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
    parent_role_id = data.get('parent_role_id')
    perm_codes = data.get('permissions', [])

    if not name:
        return jsonify({'status': 'error', 'message': 'name is required'}), 400

    tenant_id = g.current_user.tenant_id

    # Check duplicate name within same tenant
    existing = Role.query.filter_by(tenant_id=tenant_id, name=name).first()
    if existing:
        return jsonify({'status': 'error', 'message': 'Role name already exists'}), 409

    # Validate parent_role_id belongs to same tenant
    if parent_role_id is not None:
        parent = Role.query.get(parent_role_id)
        if parent is None or parent.tenant_id != tenant_id:
            return jsonify({'status': 'error', 'message': 'Invalid parent role'}), 400

    # Resolve permission codes to Permission objects
    perms = Permission.query.filter(Permission.code.in_(perm_codes)).all() if perm_codes else []

    role = Role(tenant_id=tenant_id, name=name, parent_role_id=parent_role_id)
    role.permissions = perms
    db.session.add(role)
    db.session.commit()

    return jsonify({'status': 'ok', 'data': _role_to_dict(role)}), 201


@role_bp.route('/roles', methods=['GET'])
@check_permission('role.manage')
def list_roles():
    tenant_id = g.current_user.tenant_id
    roles = Role.query.filter_by(tenant_id=tenant_id).all()
    return jsonify({'status': 'ok', 'data': [_role_to_dict(r) for r in roles]})


@role_bp.route('/roles/<int:role_id>/permissions', methods=['PUT'])
@check_permission('role.manage')
def update_role_permissions(role_id):
    role = Role.query.get(role_id)
    if role is None:
        return jsonify({'status': 'error', 'message': 'Role not found'}), 404

    tenant_id = g.current_user.tenant_id
    if role.tenant_id != tenant_id:
        return jsonify({'status': 'error', 'message': 'Role not found'}), 404

    data = request.get_json(silent=True) or {}
    parent_role_id = data.get('parent_role_id', role.parent_role_id)
    perm_codes = data.get('permissions')

    # Validate parent_role_id
    if parent_role_id is not None:
        parent = Role.query.get(parent_role_id)
        if parent is None or parent.tenant_id != tenant_id:
            return jsonify({'status': 'error', 'message': 'Invalid parent role'}), 400

    # Detect inheritance cycle
    if parent_role_id is not None and _has_cycle(role_id, parent_role_id):
        return jsonify({'status': 'error', 'message': 'Inheritance cycle detected'}), 400

    # Update parent
    role.parent_role_id = parent_role_id

    # Update permissions if provided
    if perm_codes is not None:
        # Clear existing permissions
        db.session.execute(
            role_permissions.delete().where(role_permissions.c.role_id == role_id)
        )
        # Add new permissions
        if perm_codes:
            perms = Permission.query.filter(Permission.code.in_(perm_codes)).all()
            role.permissions = perms

    db.session.commit()
    return jsonify({'status': 'ok', 'data': _role_to_dict(role)})


@role_bp.route('/users/<int:user_id>/roles', methods=['POST'])
@check_permission('role.manage')
def assign_role(user_id):
    user = User.query.get(user_id)
    if user is None:
        return jsonify({'status': 'error', 'message': 'User not found'}), 404

    tenant_id = g.current_user.tenant_id
    if user.tenant_id != tenant_id:
        return jsonify({'status': 'error', 'message': 'User not found'}), 404

    data = request.get_json(silent=True) or {}
    role_id = data.get('role_id')
    if role_id is None:
        return jsonify({'status': 'error', 'message': 'role_id is required'}), 400

    role = Role.query.get(role_id)
    if role is None or role.tenant_id != tenant_id:
        return jsonify({'status': 'error', 'message': 'Role not found'}), 404

    db.session.execute(
        user_roles.insert().values(user_id=user_id, role_id=role_id)
    )
    db.session.commit()

    return jsonify({'status': 'ok', 'data': {'user_id': user_id, 'role_id': role_id}})


@role_bp.route('/users/<int:user_id>/roles/<int:role_id>', methods=['DELETE'])
@check_permission('role.manage')
def remove_role(user_id, role_id):
    user = User.query.get(user_id)
    if user is None:
        return jsonify({'status': 'error', 'message': 'User not found'}), 404

    # Idempotent: no error if role not assigned
    db.session.execute(
        user_roles.delete().where(
            user_roles.c.user_id == user_id,
            user_roles.c.role_id == role_id
        )
    )
    db.session.commit()

    return jsonify({'status': 'ok', 'data': {'user_id': user_id, 'role_id': role_id}})
