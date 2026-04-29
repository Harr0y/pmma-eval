"""
T2 Blog — Flask App Factory & DB Initialization

This file sets up the Flask app and database. DO NOT MODIFY this file.
All business logic goes in the other modules.
"""

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
import os

db = SQLAlchemy()


def create_app():
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///blog.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    db.init_app(app)

    # Import and register models
    from models import Article, Tag

    # Import and register route blueprints
    from routes_article import article_bp
    from routes_tag import tag_bp
    app.register_blueprint(article_bp)
    app.register_blueprint(tag_bp)

    with app.app_context():
        db.create_all()

    return app


if __name__ == '__main__':
    app = create_app()
    app.run(debug=True)
