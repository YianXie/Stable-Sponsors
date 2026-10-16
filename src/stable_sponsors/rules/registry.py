from collections.abc import Callable

ENCODERS: dict[int, Callable] = {}


def register(rule_id: int) -> Callable[[Callable], Callable]:
    """A function decorator that registers a function to a specific rule ID

    Args:
        rule_id (int): the rule ID

    Returns:
        Callable[[Callable], Callable]: the function decorator
    """

    def deco(func: Callable) -> Callable:
        if rule_id in ENCODERS:
            raise ValueError(f"Rule ID {rule_id} is already registered.")
        ENCODERS[rule_id] = func
        return func

    return deco
