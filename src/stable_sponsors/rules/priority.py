from .registry import register


@register(1)
def rank_preference(ctx, params):
    raise NotImplementedError


@register(2)
def past_experience(ctx, params):
    raise NotImplementedError


@register(6)
def round_1_before_round_2(ctx, params):
    raise NotImplementedError
