"""
T2 RBAC System — Role Management Routes

Role CRUD, user-role assignment, permission management.
Register as a Flask Blueprint named 'role_bp'.
All operations require role.manage permission.
"""

from flask import Blueprint, request, jsonify, g
from models import Role, Permission, User, user_roles, role_permissions
from middleware import check_permission
from app import db

role_bp = Blueprint('role_bp', __name__)


def _role_to_dict(role):
    return {
        'id': role.id,
        'name': role.name,
        'tenant_id': role.tenant_id,
        'parent_role_id': role.parent_role_id,
        'permissions': [p.code for p in role.permissions],
    }


def _would_create_cycle(role_id, new_parent_id):
    """Check if setting new_parent_id on role_id would create an inheritance cycle."""
    if new_parent_id is None:
        return False
    if role_id == new_parent_id:
        return True
    visited = set()
    current = new_parent_id
    while current is not None:
        if current == role_id:
            return True
        if current in visited:
            return False
        visited.add(current)
        parent_role = Role.query.get(current)
        if parent_role is None:
            return False
        current = parent_role.parent_role_id
    return False


@role_bp.route('/roles', methods=['POST'])
@check_permission('role.manage')
def create_role():
    user = g.current_user
    data = request.get_json(silent=True)
    if not data or not data.get('name'):
        return jsonify({'status': 'error', 'message': 'Role name required'}), 400

    name = data['name']

    # Check duplicate name within same tenant
    existing = Role.query.filter_by(tenant_id=user.tenant_id, name=name).first()
    if existing:
        return jsonify({'status': 'error', 'message': 'Role name already exists in tenant'}), 409

    parent_role_id = data.get('parent_role_id')
    if parent_role_id is not None:
        parent = Role.query.get(parent_role_id)
        if parent is None or parent.tenant_id != user.tenant_id:
            return jsonify({'status': 'error', 'message': 'Invalid parent role'}), 400

    role = Role(tenant_id=user.tenant_id, name=name, parent_role_id=parent_role_id)

    # Assign permissions
    perm_codes = data.get('permissions', [])
    for code in perm_codes:
        perm = Permission.query.filter_by(code=code).first()
        if perm:
            role.permissions.append(perm)

    db.session.add(role)
    db.session.commit()
    return jsonify({'status': 'ok', 'data': _role_to_dict(role)}), 201


@role_bp.route('/roles', methods=['GET'])
@check_permission('role.manage')
def list_roles():
    user = g.current_user
    roles = Role.query.filter_by(tenant_id=user.tenant_id).all()
    return jsonify({'status': 'ok', 'data': [_role_to_dict(r) for r in roles]}), 200


@role_bp.route('/roles/<int:role_id>/permissions', methods=['PUT'])
@check_permission('role.manage')
def update_role_permissions(role_id):
    user = g.current_user
    role = Role.query.get(role_id)
    if role is None or role.tenant_id != user.tenant_id:
        return jsonify({'status': 'error', 'message': 'Role not found'}), 404

    data = request.get_json(silent=True)

    # Handle parent_role_id update
    if data and 'parent_role_id' in data:
        new_parent_id = data['parent_role_id']
        if new_parent_id is not None:
            parent = Role.query.get(new_parent_id)
            if parent is None or parent.tenant_id != user.tenant_id:
                return jsonify({'status': 'error', 'message': 'Invalid parent role'}), 400
            if _would_create_cycle(role_id, new_parent_id):
                return jsonify({'status': 'error', 'message': 'Inheritance cycle detected'}), 400
        role.parent_role_id = new_parent_id

    # Replace permissions
    if data and 'permissions' in data:
        role.permissions = []
        for code in data['permissions']:
            perm = Permission.query.filter_by(code=code).first()
            if perm:
                role.permissions.append(perm)

    db.session.commit()
    return jsonify({'status': 'ok', 'data': _role_to_dict(role)}), 200


@role_bp.route('/users/<int:user_id>/roles', methods=['POST'])
@check_permission('role.manage')
def assign_role(user_id):
    current = g.current_user
    target_user = User.query.get(user_id)
    if target_user is None:
        return jsonify({'status': 'error', 'message': 'User not found'}), 404

    data = request.get_json(silent=True)
    role_id = data.get('role_id')
    role = Role.query.get(role_id)
    if role is None:
        return jsonify({'status': 'error', 'message': 'Role not found'}), 404

    # Both user and role must be in same tenant
    if target_user.tenant_id != role.tenant_id:
        return jsonify({'status': 'error', 'message': 'User and role must be in same tenant'}), 403

    # Check if already assigned
    exists = db.session.query(user_roles).filter_by(
        user_id=user_id, role_id=role_id
    ).first()
    if not exists:
        db.session.execute(user_roles.insert().values(user_id=user_id, role_id=role_id))
        db.session.commit()

    return jsonify({'status': 'ok', 'data': {'user_id': user_id, 'role_id': role_id}}), 200


@role_bp.route('/users/<int:user_id>/roles/<int:role_id>', methods=['DELETE'])
@check_permission('role.manage')
def remove_role(user_id, role_id):
    target_user = User.query.get(user_id)
    if target_user is None:
        return jsonify({'status': 'error', 'message': 'User not found'}), 404

    # Idempotent delete
    db.session.execute(
        user_roles.delete().where(
            user_roles.c.user_id == user_id,
            user_roles.c.role_id == role_id,
        )
    )
    db.session.commit()
    return jsonify({'status': 'ok', 'data': None}), 200
