"""
T3 E-commerce — Authentication Middleware

Provide helper functions for authentication.

Requirements:
- get_current_user(): Read X-User-Id from request headers,
  return the User object or None if not found/invalid.
  Usage: from middleware import get_current_user
"""

from flask import request
import sys
import os
import time
sys.path.insert(0, os.path.dirname(__file__))

from models import User

# 进程内存存储：{user_id: last_order_timestamp}
_rate_limit_store = {}


def check_rate_limit(user_id):
    """检查用户是否在 10 秒内已下过单。返回 True 表示被限流。"""
    now = time.time()
    last_time = _rate_limit_store.get(user_id)
    if last_time and (now - last_time) < 10:
        return True  # 被限流
    return False  # 未被限流


def mark_order_placed(user_id):
    """记录用户下单时间（仅在订单成功创建后调用）。"""
    _rate_limit_store[user_id] = time.time()


def clear_rate_limits():
    """清理所有限流记录（用于测试隔离）。"""
    _rate_limit_store.clear()


def get_current_user():
    """Get the current user from X-User-Id header."""
    user_id = request.headers.get('X-User-Id')
    if not user_id:
        return None
    return User.query.get(int(user_id))
