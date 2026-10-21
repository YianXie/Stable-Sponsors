from stable_sponsors.rules.context import Ctx

from .registry import register


@register(1)
def rank_preference(ctx: Ctx, params: dict) -> None:
    """Reward placing teachers in higher-ranked choices.

    Args:
        ctx (Ctx): The context
        params (dict): {"weights": [...]}, the score for rank 1, 2, ... in order

    Raises:
        ValueError: If a teacher ranked a course lower than there are weights for.
    """

    weights = params["weights"]  # [7, 6, 5, 4, 3, 2, 1]
    best: dict[tuple[str, str], int] = {}
    for p in ctx.cycle.preferences:
        key = (p.teacher_id, p.course_id)
        # ranked in two rounds → keep the better rank
        best[key] = min(best.get(key, p.rank), p.rank)
    for (tid, cid), rank in best.items():
        if rank > len(weights):
            raise ValueError(
                f"{tid} ranked {cid} at {rank}; only {len(weights)} weights"
            )
        ctx.objective.append(weights[rank - 1] * ctx.x[(tid, cid)])


@register(2)
def past_experience(ctx: Ctx, params: dict) -> None:
    raise NotImplementedError


@register(6)
def round_precedence(ctx: Ctx, params: dict) -> None:
    """Reward placing teachers in a course they ranked in an earlier round.

    Args:
        ctx (Ctx): The context
        params (dict): {"bonus": {round_id: bonus}}

    Raises:
        ValueError: If a preference's round has no bonus.
    """

    bonus = params["bonus"]
    best: dict[tuple[str, str], int] = {}
    for p in ctx.cycle.preferences:
        if p.round_id not in bonus:
            raise ValueError(f"no bonus for round {p.round_id!r}")
        key = (p.teacher_id, p.course_id)
        b: int = bonus[p.round_id]
        best[key] = max(best.get(key, b), b)
    for (tid, cid), b in best.items():
        if b:
            ctx.objective.append(b * ctx.x[(tid, cid)])
