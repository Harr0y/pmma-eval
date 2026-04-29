"""
T2 RBAC System -- Role Management Routes (Sample 1: Gen 1, Developer)

All role management endpoints: create, list, update permissions/parent,
assign and remove user roles.

Design decisions (evolutionary variant):
- Cycle detection uses an iterative walk with a visited set, not recursion.
  This avoids potential stack overflow on deep inheritance chains and
  makes the control flow explicit.
- A single _resolve_permissions() helper translates permission code strings
  into Permission model instances, inserting new ones as needed. This
  decouples the API from the DB seeding order.
- Tenant scoping is enforced at the query level via Role.tenant_id filters,
  keeping every endpoint tenant-safe without extra branching.
- Error messages are intentionally vague ("Not found", "Invalid request")
  to avoid leaking information about the existence of resources in other
  tenants.

To activate: change app.py import from routes_role to routes_role_sample1.
"""

from flask import Blueprint, request, jsonify, g
from models import User, Role, Permission, role_permissions, user_roles
from app import db
from middleware import check_permission

role_bp = Blueprint('role_bp', __name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_permissions(code_list):
    """Translate a list of permission code strings to Permission ORM objects.

    Creates any Permission rows that don't exist yet so the caller never
    needs to pre-seed them.
    """
    if not code_list:
        return []
    perms = []
    for code in code_list:
        perm = Permission.query.filter_by(code=code).first()
        if perm is None:
            perm = Permission(code=code)
            db.session.add(perm)
        perms.append(perm)
    return perms


def _role_dict(role):
    """Serialise a Role to the API response dict."""
    return {
        'id': role.id,
        'name': role.name,
        'parent_role_id': role.parent_role_id,
        'permissions': [p.code for p in role.permissions],
    }


def _has_cycle(role_id, new_parent_id):
    """Detect whether setting role_id's parent to new_parent_id creates a cycle.

    Walks the parent chain from new_parent_id upward. If we ever reach
    role_id, that means role_id would be its own ancestor -- a cycle.
    Uses iteration to avoid stack limits on deep hierarchies.
    """
    if new_parent_id is None:
        return False
    visited = set()
    current = new_parent_id
    while current is not None:
        if current == role_id:
            return True
        if current in visited:
            # Already-existing cycle in data -- stop to avoid infinite loop.
            return True
        visited.add(current)
        parent_role = Role.query.get(current)
        if parent_role is None or parent_role.parent_role_id is None:
            break
        current = parent_role.parent_role_id
    return False


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@role_bp.route('/roles', methods=['POST'])
@check_permission('role.manage')
def create_role():
    user = g.current_user
    tenant_id = user.tenant_id

    data = request.get_json(silent=True)
    if not data or not isinstance(data, dict):
        return jsonify({'status': 'error', 'message': 'Invalid request'}), 400

    name = data.get('name')
    if not name or not isinstance(name, str) or not name.strip():
        return jsonify({'status': 'error', 'message': 'Role name is required'}), 400

    # Enforce unique name within tenant
    existing = Role.query.filter_by(tenant_id=tenant_id, name=name.strip()).first()
    if existing is not None:
        return jsonify({'status': 'error', 'message': 'Role already exists'}), 409

    # Validate parent_role_id belongs to same tenant
    parent_role_id = data.get('parent_role_id')
    if parent_role_id is not None:
        parent = Role.query.get(parent_role_id)
        if parent is None or parent.tenant_id != tenant_id:
            return jsonify({'status': 'error', 'message': 'Invalid parent role'}), 400

    permissions = _resolve_permissions(data.get('permissions', []))

    role = Role(
        tenant_id=tenant_id,
        name=name.strip(),
        parent_role_id=parent_role_id,
    )
    role.permissions = permissions
    db.session.add(role)
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
    tenant_id = user.tenant_id

    role = Role.query.get(role_id)
    if role is None or role.tenant_id != tenant_id:
        return jsonify({'status': 'error', 'message': 'Role not found'}), 404

    data = request.get_json(silent=True)
    if not data or not isinstance(data, dict):
        return jsonify({'status': 'error', 'message': 'Invalid request'}), 400

    # Only update parent_role_id when the key is explicitly present in the body.
    # Distinguish between "key absent" (no change) and "key present with null"
    # (clear parent) by checking key membership before reading the value.
    if 'parent_role_id' in data:
        new_parent_id = data['parent_role_id']
        if new_parent_id is not None:
            parent = Role.query.get(new_parent_id)
            if parent is None or parent.tenant_id != tenant_id:
                return jsonify({'status': 'error', 'message': 'Invalid parent role'}), 400

            if _has_cycle(role_id, new_parent_id):
                return jsonify({'status': 'error', 'message': 'Inheritance cycle detected'}), 400

        role.parent_role_id = new_parent_id

    # Replace permission set entirely
    permissions = _resolve_permissions(data.get('permissions', []))
    role.permissions = permissions

    db.session.commit()

    return jsonify({'status': 'ok', 'data': _role_dict(role)})


@role_bp.route('/users/<int:user_id>/roles', methods=['POST'])
@check_permission('role.manage')
def assign_role(user_id):
    current_user = g.current_user
    tenant_id = current_user.tenant_id

    target_user = User.query.get(user_id)
    if target_user is None or target_user.tenant_id != tenant_id:
        return jsonify({'status': 'error', 'message': 'User not found'}), 404

    data = request.get_json(silent=True)
    if not data or not isinstance(data, dict):
        return jsonify({'status': 'error', 'message': 'Invalid request'}), 400

    role_id = data.get('role_id')
    if role_id is None:
        return jsonify({'status': 'error', 'message': 'role_id is required'}), 400

    role = Role.query.get(role_id)
    if role is None or role.tenant_id != tenant_id:
        return jsonify({'status': 'error', 'message': 'Role not found'}), 404

    # Use a raw insert via the association table to avoid SQLAlchemy
    # trying to re-fetch and duplicate the collection.
    exists = db.session.execute(
        user_roles.select().where(
            user_roles.c.user_id == user_id,
            user_roles.c.role_id == role_id,
        )
    ).fetchone()

    if not exists:
        db.session.execute(
            user_roles.insert().values(user_id=user_id, role_id=role_id)
        )
        db.session.commit()

    return jsonify({'status': 'ok', 'data': {'user_id': user_id, 'role_id': role_id}})


@role_bp.route('/users/<int:user_id>/roles/<int:role_id>', methods=['DELETE'])
@check_permission('role.manage')
def remove_role(user_id, role_id):
    current_user = g.current_user
    tenant_id = current_user.tenant_id

    target_user = User.query.get(user_id)
    if target_user is None or target_user.tenant_id != tenant_id:
        return jsonify({'status': 'error', 'message': 'User not found'}), 404

    # Idempotent: delete silently even if the association doesn't exist.
    db.session.execute(
        user_roles.delete().where(
            user_roles.c.user_id == user_id,
            user_roles.c.role_id == role_id,
        )
    )
    db.session.commit()

    return jsonify({'status': 'ok', 'data': {'user_id': user_id, 'role_id': role_id}})
