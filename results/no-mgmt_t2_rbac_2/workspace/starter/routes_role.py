"""
T2 RBAC System — Role Management Routes

Role CRUD, user-role assignment, permission management.
Register as a Flask Blueprint named 'role_bp'.
All operations require role.manage permission.

IMPORTANT: Role inheritance is handled by middleware._collect_role_permissions().
Roles are tenant-scoped. This module works with middleware.py and routes_document.py.
"""

from flask import Blueprint, request, jsonify, g
from models import Role, Permission, User, role_permissions
from app import db
from middleware import check_permission

role_bp = Blueprint('role_bp', __name__)


def _role_dict(role):
    return {
        'id': role.id,
        'name': role.name,
        'parent_role_id': role.parent_role_id,
        'permissions': [p.code for p in role.permissions],
    }


def _would_create_cycle(role_id, new_parent_id):
    """Check if setting new_parent_id on role_id would create a cycle."""
    if new_parent_id is None:
        return False
    visited = set()
    current = new_parent_id
    while current is not None:
        if current == role_id:
            return True
        if current in visited:
            return False
        visited.add(current)
        role = Role.query.get(current)
        if role is None:
            return False
        current = role.parent_role_id
    return False


@role_bp.route('/roles', methods=['POST'])
@check_permission('role.manage')
def create_role():
    user = g.current_user
    data = request.get_json(silent=True) or {}
    name = data.get('name')
    if not name:
        return jsonify({'status': 'error', 'message': 'Role name is required'}), 400

    # Check duplicate name within same tenant
    existing = Role.query.filter_by(tenant_id=user.tenant_id, name=name).first()
    if existing:
        return jsonify({'status': 'error', 'message': 'Role name already exists'}), 409

    parent_role_id = data.get('parent_role_id')
    if parent_role_id is not None:
        parent = Role.query.get(parent_role_id)
        if parent is None or parent.tenant_id != user.tenant_id:
            return jsonify({'status': 'error', 'message': 'Invalid parent role'}), 400

    role = Role(tenant_id=user.tenant_id, name=name, parent_role_id=parent_role_id)
    db.session.add(role)
    db.session.flush()

    perm_codes = data.get('permissions', [])
    if perm_codes:
        perms = Permission.query.filter(Permission.code.in_(perm_codes)).all()
        role.permissions = perms

    db.session.commit()
    return jsonify({'status': 'ok', 'data': _role_dict(role)}), 201


@role_bp.route('/roles', methods=['GET'])
@check_permission('role.manage')
def list_roles():
    user = g.current_user
    roles = Role.query.filter_by(tenant_id=user.tenant_id).all()
    return jsonify({'status': 'ok', 'data': [_role_dict(r) for r in roles]})


@role_bp.route('/roles/<int:role_id>/permissions', methods=['PUT'])
@check_permission('role.manage')
def update_role_permissions(role_id):
    user = g.current_user
    role = Role.query.get(role_id)
    if role is None or role.tenant_id != user.tenant_id:
        return jsonify({'status': 'error', 'message': 'Role not found'}), 404

    data = request.get_json(silent=True) or {}

    # Handle parent_role_id update
    if 'parent_role_id' in data:
        new_parent_id = data['parent_role_id']
        if new_parent_id is not None:
            parent = Role.query.get(new_parent_id)
            if parent is None or parent.tenant_id != user.tenant_id:
                return jsonify({'status': 'error', 'message': 'Invalid parent role'}), 400
            if _would_create_cycle(role_id, new_parent_id):
                return jsonify({'status': 'error', 'message': 'Inheritance cycle detected'}), 400
        role.parent_role_id = new_parent_id

    # Handle permissions update
    if 'permissions' in data:
        perm_codes = data['permissions']
        perms = Permission.query.filter(Permission.code.in_(perm_codes)).all()
        role.permissions = perms

    db.session.commit()
    return jsonify({'status': 'ok', 'data': _role_dict(role)})


@role_bp.route('/users/<int:user_id>/roles', methods=['POST'])
@check_permission('role.manage')
def assign_role(user_id):
    user = g.current_user
    target_user = User.query.get(user_id)
    if target_user is None or target_user.tenant_id != user.tenant_id:
        return jsonify({'status': 'error', 'message': 'User not found'}), 404

    data = request.get_json(silent=True) or {}
    role_id = data.get('role_id')
    role = Role.query.get(role_id)
    if role is None or role.tenant_id != user.tenant_id:
        return jsonify({'status': 'error', 'message': 'Role not found'}), 404

    if role not in target_user.roles:
        target_user.roles.append(role)
        db.session.commit()

    return jsonify({'status': 'ok', 'data': {'user_id': user_id, 'role_id': role_id}})


@role_bp.route('/users/<int:user_id>/roles/<int:role_id>', methods=['DELETE'])
@check_permission('role.manage')
def remove_role(user_id):
    user = g.current_user
    target_user = User.query.get(user_id)
    if target_user is None or target_user.tenant_id != user.tenant_id:
        return jsonify({'status': 'error', 'message': 'User not found'}), 404

    role = Role.query.get(role_id)
    if role is not None and role in target_user.roles:
        target_user.roles.remove(role)
        db.session.commit()

    return jsonify({'status': 'ok', 'data': None})
