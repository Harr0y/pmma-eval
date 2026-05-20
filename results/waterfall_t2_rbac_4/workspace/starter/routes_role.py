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
from middleware import check_permission
from app import db

role_bp = Blueprint('role_bp', __name__)


def _serialize_role(role):
    """Serialize a role object to a dict with permission codes."""
    return {
        'id': role.id,
        'name': role.name,
        'parent_role_id': role.parent_role_id,
        'permissions': [p.code for p in role.permissions]
    }


def _detect_cycle(role_id, target_parent_id):
    """Check if setting role_id's parent to target_parent_id would create a cycle.

    Traverses upward from target_parent_id. If role_id is encountered in the
    chain, a cycle would form. Also guards against pre-existing cycles via
    the visited set.
    """
    current = target_parent_id
    visited = set()
    while current is not None:
        if current == role_id:
            return True  # Would form a cycle
        if current in visited:
            return False  # Pre-existing cycle, but not involving role_id
        visited.add(current)
        role = Role.query.get(current)
        if role:
            current = role.parent_role_id
        else:
            break
    return False


@role_bp.route('/roles', methods=['POST'])
@check_permission('role.manage')
def create_role():
    """Create a new role in the current tenant.

    Validates: name non-empty, unique within tenant, parent exists and is
    same-tenant, and all permission codes exist in the Permission table.
    """
    data = request.get_json(silent=True)
    if data is None:
        return jsonify({'status': 'error', 'message': 'Invalid request'}), 400

    name = data.get('name')
    if not name:
        return jsonify({'status': 'error', 'message': 'name is required'}), 400

    tenant_id = g.current_user.tenant_id

    # Check duplicate role name within same tenant
    existing = Role.query.filter_by(tenant_id=tenant_id, name=name).first()
    if existing:
        return jsonify({'status': 'error', 'message': 'Role name already exists in this tenant'}), 409

    # Validate parent_role_id if provided
    parent_role_id = data.get('parent_role_id')
    if parent_role_id is not None:
        parent = Role.query.get(parent_role_id)
        if parent is None or parent.tenant_id != tenant_id:
            return jsonify({'status': 'error', 'message': 'Parent role not found or belongs to a different tenant'}), 400

    # Validate permission codes if provided
    permissions = data.get('permissions', [])
    if permissions:
        valid_perms = Permission.query.filter(Permission.code.in_(permissions)).all()
        valid_codes = {p.code for p in valid_perms}
        invalid_codes = set(permissions) - valid_codes
        if invalid_codes:
            return jsonify({'status': 'error', 'message': f'Invalid permission codes: {", ".join(sorted(invalid_codes))}'}), 400

    # Create role
    role = Role(tenant_id=tenant_id, name=name, parent_role_id=parent_role_id)
    db.session.add(role)
    db.session.flush()  # Get role.id

    # Associate permissions
    if permissions:
        perm_records = Permission.query.filter(Permission.code.in_(permissions)).all()
        for perm in perm_records:
            db.session.execute(
                role_permissions.insert().values(role_id=role.id, permission_id=perm.id)
            )

    db.session.commit()
    return jsonify({'status': 'ok', 'data': _serialize_role(role)}), 201


@role_bp.route('/roles', methods=['GET'])
@check_permission('role.manage')
def list_roles():
    """List all roles for the current tenant, including permission codes."""
    tenant_id = g.current_user.tenant_id
    roles = Role.query.filter_by(tenant_id=tenant_id).all()
    return jsonify({'status': 'ok', 'data': [_serialize_role(r) for r in roles]}), 200


@role_bp.route('/roles/<int:role_id>/permissions', methods=['PUT'])
@check_permission('role.manage')
def update_role_permissions(role_id):
    """Update a role's permission set and/or parent role.

    Partial update semantics: only fields present in the request body are
    updated. An empty request body returns the current role unchanged.

    Cycle detection: when setting parent_role_id, traverses upward from the
    target parent to ensure the current role is not in the ancestor chain.
    """
    role = Role.query.get(role_id)
    if role is None:
        return jsonify({'status': 'error', 'message': 'Role not found'}), 404

    tenant_id = g.current_user.tenant_id

    data = request.get_json(silent=True)
    if data is None:
        data = {}

    # Partial update: permissions
    if 'permissions' in data:
        new_perms = data['permissions']

        # Validate all permission codes exist
        if new_perms:
            valid_perms = Permission.query.filter(Permission.code.in_(new_perms)).all()
            valid_codes = {p.code for p in valid_perms}
            invalid_codes = set(new_perms) - valid_codes
            if invalid_codes:
                return jsonify({'status': 'error', 'message': f'Invalid permission codes: {", ".join(sorted(invalid_codes))}'}), 400

        # Clear old permissions and set new ones
        db.session.execute(
            role_permissions.delete().where(role_permissions.c.role_id == role.id)
        )

        if new_perms:
            perm_records = Permission.query.filter(Permission.code.in_(new_perms)).all()
            for perm in perm_records:
                db.session.execute(
                    role_permissions.insert().values(role_id=role.id, permission_id=perm.id)
                )

    # Partial update: parent_role_id
    if 'parent_role_id' in data:
        new_parent_id = data['parent_role_id']

        if new_parent_id is not None:
            parent = Role.query.get(new_parent_id)
            if parent is None or parent.tenant_id != tenant_id:
                return jsonify({'status': 'error', 'message': 'Parent role not found or belongs to a different tenant'}), 400

            # Cycle detection: would setting role's parent to new_parent_id create a loop?
            if _detect_cycle(role.id, new_parent_id):
                return jsonify({'status': 'error', 'message': 'Inheritance cycle detected'}), 400

        role.parent_role_id = new_parent_id

    db.session.commit()
    return jsonify({'status': 'ok', 'data': _serialize_role(role)}), 200


@role_bp.route('/users/<int:user_id>/roles', methods=['POST'])
@check_permission('role.manage')
def assign_role_to_user(user_id):
    """Assign a role to a user.

    Both the target user and the role must belong to the same tenant.
    """
    data = request.get_json(silent=True)
    if data is None:
        return jsonify({'status': 'error', 'message': 'Invalid request'}), 400

    role_id = data.get('role_id')
    if role_id is None:
        return jsonify({'status': 'error', 'message': 'role_id is required'}), 400

    # Look up target user
    target_user = User.query.get(user_id)
    if target_user is None:
        return jsonify({'status': 'error', 'message': 'User not found'}), 404

    # Look up role
    role = Role.query.get(role_id)
    if role is None:
        return jsonify({'status': 'error', 'message': 'Role not found'}), 404

    # Cross-tenant check: user and role must belong to the same tenant
    if target_user.tenant_id != role.tenant_id:
        return jsonify({'status': 'error', 'message': 'User and role must belong to the same tenant'}), 403

    # Add association (ignore if already exists)
    db.session.execute(
        user_roles.insert().values(user_id=user_id, role_id=role_id)
    )
    db.session.commit()
    return jsonify({'status': 'ok', 'data': None}), 200


@role_bp.route('/users/<int:user_id>/roles/<int:role_id>', methods=['DELETE'])
@check_permission('role.manage')
def remove_role_from_user(user_id, role_id):
    """Remove a role from a user.

    Idempotent: no error if the role is not currently assigned.
    Cross-tenant protection: if the target user belongs to a different tenant,
    returns 404.
    """
    target_user = User.query.get(user_id)
    if target_user is None:
        return jsonify({'status': 'error', 'message': 'User not found'}), 404

    # Cross-tenant protection
    if target_user.tenant_id != g.current_user.tenant_id:
        return jsonify({'status': 'error', 'message': 'User not found'}), 404

    # Delete association (idempotent — no error if not found)
    db.session.execute(
        user_roles.delete().where(
            (user_roles.c.user_id == user_id) & (user_roles.c.role_id == role_id)
        )
    )
    db.session.commit()
    return jsonify({'status': 'ok', 'data': None}), 200
