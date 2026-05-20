"""
T2 RBAC System — Flask App Factory & DB Initialization

This file sets up the Flask app and database. DO NOT MODIFY this file.
All business logic goes in the other modules.
"""

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
import os

db = SQLAlchemy()


def create_app():
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///rbac.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['JWT_SECRET'] = os.environ.get('JWT_SECRET', 'dev-secret-key')
    app.config['JWT_EXPIRY_HOURS'] = int(os.environ.get('JWT_EXPIRY_HOURS', '24'))

    db.init_app(app)

    # Import and register models
    from models import Tenant, User, Role, Permission, Document

    # Import and register route blueprints
    from routes_auth import auth_bp
    from routes_document import document_bp
    from routes_role import role_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(document_bp)
    app.register_blueprint(role_bp)

    with app.app_context():
        db.create_all()

    return app


if __name__ == '__main__':
    app = create_app()
    app.run(debug=True)
