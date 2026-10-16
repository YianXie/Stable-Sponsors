from .registry import register


@register(7)
def tie_break(ctx, params):
    raise NotImplementedError
