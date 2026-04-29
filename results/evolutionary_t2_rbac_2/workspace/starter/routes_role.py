"""
T2 RBAC System -- Role Management Routes (Gen 1 Sample 1 Variant)

Evolutionary approach: recursive cycle detection, independent permission
resolution helper, batch permission insertion via association table inserts.

Register as a Flask Blueprint named 'role_bp'.
All operations require role.manage permission.

Key design decisions (Sample 1 signature):
- Cycle detection uses a recursive _would_create_cycle() function that
  walks the parent chain from new_parent_id looking for role_id
- Permission resolution is extracted into _resolve_permissions() which
  maps permission codes to Permission IDs with validation
- Batch inserts via db.session.execute(role_permissions.insert())
- Helper functions return (data, data, error_response) tuples for clean
  separation of validation from business logic
"""

from flask import Blueprint, request, jsonify, g
from sqlalchemy import select, and_

from models import Role, Permission, User, role_permissions, user_roles
from middleware import check_permission
from app import db

role_bp = Blueprint('role_bp', __name__)


# ============================================================
# Helper Functions
# ============================================================


def _would_create_cycle(role_id, new_parent_id):
    """Check if setting new_parent_id as parent of role_id would create a cycle.

    Walks up the parent chain from new_parent_id. If we encounter role_id,
    then making new_parent_id the parent of role_id would form a cycle.

    Args:
        role_id: The role being updated (the potential child).
        new_parent_id: The proposed new parent role.

    Returns:
        True if a cycle would be created, False otherwise.
    """
    if new_parent_id is None:
        return False

    visited = set()
    current_id = new_parent_id

    while current_id is not None:
        if current_id == role_id:
            return True
        if current_id in visited:
            # Already visited -- should not happen in valid data, but safety guard
            return True
        visited.add(current_id)

        role = db.session.get(Role, current_id)
        if role is None:
            break
        current_id = role.parent_role_id

    return False


def _resolve_permissions(perm_codes, tenant_id=None):
    """Map permission code strings to Permission model instances.

    Looks up each permission code in the database. Validates that all
    codes correspond to existing permissions.

    Args:
        perm_codes: List of permission code strings (e.g. ['doc.read', 'doc.write']).
        tenant_id: Unused parameter kept for API consistency with potential
                   future tenant-scoped permissions.

    Returns:
        (permissions, error_response) tuple.
        On success: (list of Permission objects, None)
        On failure: (None, (jsonify response, status_code))
    """
    if not isinstance(perm_codes, list):
        return None, (jsonify({'status': 'error', 'message': 'permissions must be a list'}), 400)

    permissions = []
    for code in perm_codes:
        perm = Permission.query.filter_by(code=code).first()
        if perm is None:
            return None, (
                jsonify({'status': 'error', 'message': f'Unknown permission: {code}'}),
                400,
            )
        permissions.append(perm)

    return permissions, None


def _serialize_role(role):
    """Serialize a Role model instance into a JSON-safe dict.

    Includes id, name, tenant_id, parent_role_id, and permission codes.
    """
    return {
        'id': role.id,
        'name': role.name,
        'tenant_id': role.tenant_id,
        'parent_role_id': role.parent_role_id,
        'permissions': [p.code for p in role.permissions],
    }


def _get_current_tenant_id():
    """Extract tenant_id from the authenticated user stored in g."""
    return g.current_user.tenant_id


# ============================================================
# POST /roles -- Create Role
# ============================================================


@role_bp.route('/roles', methods=['POST'])
@check_permission('role.manage')
def create_role():
    """POST /roles -- Create a new role within the current tenant.

    Request body (JSON):
        {"name": str, "parent_role_id": int|null, "permissions": [str, ...]}

    Success (201):
        {"status": "ok", "data": {"id": int, "name": str, "parent_role_id": int|null,
                  "permissions": [str, ...]}}

    Errors:
        400 -- Missing name, invalid parent, or unknown permissions
        403 -- Insufficient permissions
        409 -- Duplicate role name within the same tenant
    """
    body = request.get_json(silent=True)

    # Step 1: Validate request body structure
    if not isinstance(body, dict):
        return jsonify({'status': 'error', 'message': 'Request body must be a JSON object'}), 400

    name = body.get('name')
    if not name or not isinstance(name, str):
        return jsonify({'status': 'error', 'message': 'Missing or invalid name'}), 400

    tenant_id = _get_current_tenant_id()

    # Step 2: Check for duplicate name within the same tenant
    existing = Role.query.filter_by(tenant_id=tenant_id, name=name).first()
    if existing is not None:
        return jsonify({'status': 'error', 'message': 'Role name already exists in this tenant'}), 409

    # Step 3: Validate parent_role_id if provided
    parent_role_id = body.get('parent_role_id')
    if parent_role_id is not None:
        parent_role = db.session.get(Role, parent_role_id)
        if parent_role is None:
            return jsonify({'status': 'error', 'message': 'Parent role not found'}), 400
        if parent_role.tenant_id != tenant_id:
            return jsonify({'status': 'error', 'message': 'Parent role must belong to the same tenant'}), 400

    # Step 4: Resolve permissions
    perm_codes = body.get('permissions', [])
    permissions, perm_error = _resolve_permissions(perm_codes, tenant_id)
    if perm_error:
        return perm_error

    # Step 5: Create the role
    role = Role(tenant_id=tenant_id, name=name, parent_role_id=parent_role_id)
    db.session.add(role)
    db.session.flush()  # Flush to get role.id for permission insertion

    # Step 6: Batch insert permissions via association table
    if permissions:
        db.session.execute(
            role_permissions.insert().values(
                [(role.id, p.id) for p in permissions]
            )
        )

    db.session.commit()

    return jsonify({
        'status': 'ok',
        'data': _serialize_role(role),
    }), 201


# ============================================================
# GET /roles -- List Roles
# ============================================================


@role_bp.route('/roles', methods=['GET'])
@check_permission('role.manage')
def list_roles():
    """GET /roles -- List all roles for the current tenant.

    Success (200):
        {"status": "ok", "data": [{"id": int, "name": str, "tenant_id": int,
                  "parent_role_id": int|null, "permissions": [str, ...]}, ...]}

    Errors:
        403 -- Insufficient permissions
    """
    tenant_id = _get_current_tenant_id()
    roles = Role.query.filter_by(tenant_id=tenant_id).all()

    return jsonify({
        'status': 'ok',
        'data': [_serialize_role(role) for role in roles],
    }), 200


# ============================================================
# PUT /roles/<id>/permissions -- Update Permissions & Parent
# ============================================================


@role_bp.route('/roles/<int:role_id>/permissions', methods=['PUT'])
@check_permission('role.manage')
def update_role_permissions(role_id):
    """PUT /roles/<id>/permissions -- Replace permission set and update parent.

    Request body (JSON):
        {"permissions": [str, ...], "parent_role_id": int|null}

    Success (200):
        {"status": "ok", "data": {"id": int, "name": str, "tenant_id": int,
                  "parent_role_id": int|null, "permissions": [str, ...]}}

    Errors:
        400 -- Cycle detected, invalid parent, or unknown permissions
        403 -- Insufficient permissions
        404 -- Role not found
    """
    role = db.session.get(Role, role_id)
    if role is None:
        return jsonify({'status': 'error', 'message': 'Role not found'}), 404

    body = request.get_json(silent=True)

    # Step 1: Validate request body structure
    if not isinstance(body, dict):
        return jsonify({'status': 'error', 'message': 'Request body must be a JSON object'}), 400

    tenant_id = _get_current_tenant_id()

    # Step 2: Handle parent_role_id update if provided
    parent_role_id = body.get('parent_role_id')
    if parent_role_id is not None:
        # Validate parent exists and belongs to same tenant
        parent_role = db.session.get(Role, parent_role_id)
        if parent_role is None:
            return jsonify({'status': 'error', 'message': 'Parent role not found'}), 400
        if parent_role.tenant_id != tenant_id:
            return jsonify({'status': 'error', 'message': 'Parent role must belong to the same tenant'}), 400

        # Check for inheritance cycle
        if _would_create_cycle(role_id, parent_role_id):
            return jsonify({'status': 'error', 'message': 'Setting this parent would create an inheritance cycle'}), 400

        role.parent_role_id = parent_role_id
    elif 'parent_role_id' in body:
        # Explicitly set to null if key is present but value is None
        role.parent_role_id = None

    # Step 3: Resolve new permissions if provided
    perm_codes = body.get('permissions')
    if perm_codes is not None:
        permissions, perm_error = _resolve_permissions(perm_codes, tenant_id)
        if perm_error:
            return perm_error

        # Delete existing permissions and insert new ones
        db.session.execute(
            role_permissions.delete().where(role_permissions.c.role_id == role_id)
        )
        if permissions:
            db.session.execute(
                role_permissions.insert().values(
                    [(role_id, p.id) for p in permissions]
                )
            )

    db.session.commit()

    # Refresh role to pick up updated permissions
    db.session.refresh(role)

    return jsonify({
        'status': 'ok',
        'data': _serialize_role(role),
    }), 200


# ============================================================
# POST /users/<id>/roles -- Assign Role to User
# ============================================================


@role_bp.route('/users/<int:user_id>/roles', methods=['POST'])
@check_permission('role.manage')
def assign_role_to_user(user_id):
    """POST /users/<id>/roles -- Assign a role to a user.

    Request body (JSON):
        {"role_id": int}

    Success (200):
        {"status": "ok", "data": {"message": "Role assigned"}}

    Errors:
        403 -- Insufficient permissions or cross-tenant assignment
        404 -- User or role not found
    """
    # Step 1: Validate user exists and belongs to same tenant
    user = db.session.get(User, user_id)
    if user is None:
        return jsonify({'status': 'error', 'message': 'User not found'}), 404

    tenant_id = _get_current_tenant_id()
    if user.tenant_id != tenant_id:
        return jsonify({'status': 'error', 'message': 'User not found'}), 404

    # Step 2: Parse and validate request body
    body = request.get_json(silent=True)
    if not isinstance(body, dict) or 'role_id' not in body:
        return jsonify({'status': 'error', 'message': 'Missing role_id'}), 400

    role_id = body.get('role_id')
    if not isinstance(role_id, int):
        return jsonify({'status': 'error', 'message': 'role_id must be an integer'}), 400

    # Step 3: Validate role exists and belongs to same tenant
    role = db.session.get(Role, role_id)
    if role is None:
        return jsonify({'status': 'error', 'message': 'Role not found'}), 404

    if role.tenant_id != tenant_id:
        return jsonify({'status': 'error', 'message': 'Role not found'}), 404

    # Step 4: Insert the user-role association (ignore duplicates silently)
    db.session.execute(
        user_roles.insert().values(user_id=user_id, role_id=role_id)
    )
    db.session.commit()

    return jsonify({
        'status': 'ok',
        'data': {'message': 'Role assigned'},
    }), 200


# ============================================================
# DELETE /users/<id>/roles/<role_id> -- Remove Role from User
# ============================================================


@role_bp.route('/users/<int:user_id>/roles/<int:role_id>', methods=['DELETE'])
@check_permission('role.manage')
def remove_role_from_user(user_id, role_id):
    """DELETE /users/<id>/roles/<role_id> -- Remove a role from a user.

    This is an idempotent operation: removing a role that was never assigned
    still returns 200.

    Success (200):
        {"status": "ok", "data": {"message": "Role removed"}}

    Errors:
        403 -- Insufficient permissions
        404 -- User not found
    """
    # Step 1: Validate user exists and belongs to same tenant
    user = db.session.get(User, user_id)
    if user is None:
        return jsonify({'status': 'error', 'message': 'User not found'}), 404

    tenant_id = _get_current_tenant_id()
    if user.tenant_id != tenant_id:
        return jsonify({'status': 'error', 'message': 'User not found'}), 404

    # Step 2: Delete the user-role association (idempotent -- no error if not found)
    db.session.execute(
        user_roles.delete().where(
            and_(
                user_roles.c.user_id == user_id,
                user_roles.c.role_id == role_id,
            )
        )
    )
    db.session.commit()

    return jsonify({
        'status': 'ok',
        'data': {'message': 'Role removed'},
    }), 200
