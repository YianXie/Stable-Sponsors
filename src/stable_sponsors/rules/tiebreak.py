from stable_sponsors.rules.context import Ctx

from .registry import register


@register(7)
def tie_break(ctx: Ctx, params: dict) -> None:
    raise NotImplementedError
