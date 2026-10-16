from .registry import register


@register(0)
def incumbency_preassignment(ctx, params):
    raise NotImplementedError


@register(3)
def qualification_required(ctx, params):
    raise NotImplementedError


@register(4)
def only_ranked_courses(ctx, params):
    raise NotImplementedError


@register(5)
def slot_gender(ctx, params):
    raise NotImplementedError
