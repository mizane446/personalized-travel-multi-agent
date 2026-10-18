"""Doubao direct HTTP backend for Hermes' native web_search tool."""
from .provider import DoubaoSearchProvider


def register(ctx):
    ctx.register_web_search_provider(DoubaoSearchProvider())
