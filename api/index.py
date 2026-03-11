"""
api/index.py — Vercel Serverless Python 入口

Vercel 通过此文件找到 Flask WSGI app。
路由配置见根目录 vercel.json。
"""
import sys
import os

# 将项目根目录加入 Python 路径，确保模块可以正确 import
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)

from dashboard.app import app  # noqa: E402

# Vercel Python Runtime 自动识别名为 `app` 的 WSGI callable，无需额外声明 handler
