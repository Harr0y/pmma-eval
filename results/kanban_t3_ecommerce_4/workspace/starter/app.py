"""
T3 E-commerce — Flask App Factory & DB Initialization

This file sets up the Flask app and database. DO NOT MODIFY this file.
All business logic goes in the other modules.
"""

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
import os

db = SQLAlchemy()


def create_app():
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///ecommerce.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    db.init_app(app)

    # Import and register models
    from models import User, Product, Order

    # Import and register route blueprints
    from routes_product import product_bp
    from routes_order import order_bp
    app.register_blueprint(product_bp)
    app.register_blueprint(order_bp)

    with app.app_context():
        db.create_all()
        # Seed initial users
        if not User.query.filter_by(username='admin').first():
            db.session.add(User(username='admin', role='admin'))
            db.session.add(User(username='user1', role='user'))
            db.session.commit()

    return app


if __name__ == '__main__':
    app = create_app()
    app.run(debug=True)
