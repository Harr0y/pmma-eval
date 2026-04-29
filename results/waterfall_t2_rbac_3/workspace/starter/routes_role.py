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

from middleware import check_permission
from models import Role, Permission, User
from app import db

role_bp = Blueprint('role_bp', __name__)


def _serialize_role(role):
    """Serialize a Role model instance to a JSON-compatible dict.
    See design.md section 4.3.
    """
    return {
        "id": role.id,
        "name": role.name,
        "parent_role_id": role.parent_role_id,
        "permissions": [p.code for p in role.permissions]
    }


def _would_create_cycle(role_id, new_parent_id):
    """Check if setting role_id's parent to new_parent_id would create a cycle.
    Traverses from new_parent_id up the parent chain.
    If role_id is encountered, a cycle exists.
    See design.md section 4.1.
    """
    visited = {role_id}
    current = new_parent_id
    while current is not None:
        if current in visited:
            return True  # Cycle detected!
        visited.add(current)
        role = Role.query.get(current)
        if role is None:
            return False  # Chain broken, no cycle
        current = role.parent_role_id
    return False


@role_bp.route('/roles', methods=['POST'])
@check_permission('role.manage')
def create_role():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'status': 'error', 'message': 'Request body must be JSON'}), 400

    name = data.get('name')
    if not name:
        return jsonify({'status': 'error', 'message': 'Role name is required'}), 400

    permissions = data.get('permissions', [])
    parent_role_id = data.get('parent_role_id')

    # Check duplicate role name within same tenant
    existing = Role.query.filter_by(tenant_id=g.current_user.tenant_id, name=name).first()
    if existing:
        return jsonify({'status': 'error', 'message': 'Role name already exists in this tenant'}), 409

    # Validate parent_role_id if provided and not null
    if parent_role_id is not None:
        parent_role = Role.query.get(parent_role_id)
        if not parent_role or parent_role.tenant_id != g.current_user.tenant_id:
            return jsonify({'status': 'error', 'message': 'Parent role not found or not in same tenant'}), 400

    # Query Permission records for each code in permissions list
    perm_records = []
    if permissions:
        perm_records = Permission.query.filter(Permission.code.in_(permissions)).all()
        found_codes = {p.code for p in perm_records}
        missing = set(permissions) - found_codes
        if missing:
            return jsonify({'status': 'error', 'message': f'Permissions not found: {", ".join(sorted(missing))}'}), 400

    # Create role
    role = Role(
        tenant_id=g.current_user.tenant_id,
        name=name,
        parent_role_id=parent_role_id,
    )
    role.permissions = perm_records
    db.session.add(role)
    db.session.commit()

    return jsonify({'status': 'ok', 'data': _serialize_role(role)}), 201


@role_bp.route('/roles', methods=['GET'])
@check_permission('role.manage')
def list_roles():
    roles = Role.query.filter_by(tenant_id=g.current_user.tenant_id).all()
    return jsonify({'status': 'ok', 'data': [_serialize_role(r) for r in roles]}), 200


@role_bp.route('/roles/<int:role_id>/permissions', methods=['PUT'])
@check_permission('role.manage')
def update_role_permissions(role_id):
    role = Role.query.get(role_id)
    if not role:
        return jsonify({'status': 'error', 'message': 'Role not found'}), 404

    data = request.get_json(silent=True)
    if not data:
        return jsonify({'status': 'error', 'message': 'Request body must be JSON'}), 400

    # Handle parent_role_id update if provided
    if 'parent_role_id' in data:
        new_parent_id = data['parent_role_id']
        if new_parent_id is not None:
            # Validate parent role exists and belongs to same tenant
            parent_role = Role.query.get(new_parent_id)
            if not parent_role or parent_role.tenant_id != g.current_user.tenant_id:
                return jsonify({'status': 'error', 'message': 'Parent role not found or not in same tenant'}), 400
            # Cycle detection
            if _would_create_cycle(role_id, new_parent_id):
                return jsonify({'status': 'error', 'message': 'Setting this parent would create an inheritance cycle'}), 400
        role.parent_role_id = new_parent_id

    # Handle permissions update if provided
    if 'permissions' in data:
        perm_codes = data['permissions']
        perm_records = []
        if perm_codes:
            perm_records = Permission.query.filter(Permission.code.in_(perm_codes)).all()
            found_codes = {p.code for p in perm_records}
            missing = set(perm_codes) - found_codes
            if missing:
                return jsonify({'status': 'error', 'message': f'Permissions not found: {", ".join(sorted(missing))}'}), 400
        role.permissions = perm_records

    db.session.commit()

    return jsonify({'status': 'ok', 'data': _serialize_role(role)}), 200


@role_bp.route('/users/<int:user_id>/roles', methods=['POST'])
@check_permission('role.manage')
def assign_role(user_id):
    user = User.query.get(user_id)
    if not user:
        return jsonify({'status': 'error', 'message': 'User not found'}), 404

    data = request.get_json(silent=True)
    if not data:
        return jsonify({'status': 'error', 'message': 'Request body must be JSON'}), 400

    role_id = data.get('role_id')
    if role_id is None:
        return jsonify({'status': 'error', 'message': 'role_id is required'}), 400

    role = Role.query.get(role_id)
    if not role:
        return jsonify({'status': 'error', 'message': 'Role not found'}), 404

    # Cross-tenant check
    if user.tenant_id != role.tenant_id:
        return jsonify({'status': 'error', 'message': 'User and role must belong to the same tenant'}), 403

    # Idempotent: if already assigned, just return success
    if role not in user.roles:
        user.roles.append(role)
        db.session.commit()

    return jsonify({'status': 'ok', 'data': None}), 200


@role_bp.route('/users/<int:user_id>/roles/<int:role_id>', methods=['DELETE'])
@check_permission('role.manage')
def remove_role(user_id, role_id):
    user = User.query.get(user_id)
    if not user:
        return jsonify({'status': 'error', 'message': 'User not found'}), 404

    role = Role.query.get(role_id)

    # Idempotent: if role doesn't exist or not assigned, just return success
    if role and role in user.roles:
        user.roles.remove(role)
        db.session.commit()

    return jsonify({'status': 'ok', 'data': None}), 200
