"""Travel capabilities implemented through Hermes' public plugin surfaces."""


def register(ctx):
    from .integration import register_tools
    register_tools(ctx)
