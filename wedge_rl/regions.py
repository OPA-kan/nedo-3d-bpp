"""Region registry: the environments a local executor can be trained on.

Lives in its own module (not ``__main__``) because the factory is pickled
into spawned worker processes, which must be able to import the class by
its qualified name.
"""

from __future__ import annotations

REGIONS = ("wedge", "shelf")
DEFAULT_LAYOUT = {"wedge": "c1", "shelf": "c1s"}


def make_env(region: str, layout: str, n_items: int, seed: int = 0):
    if region == "wedge":
        from .env import WedgeEnv

        return WedgeEnv(layout, n_items=n_items, seed=seed)
    if region == "shelf":
        from .shelf import ShelfEnv

        return ShelfEnv(layout, n_items=n_items, seed=seed)
    raise KeyError(f"unknown region {region!r}; known: {REGIONS}")


class EnvFactory:
    """A picklable zero-argument constructor for the worker processes."""

    def __init__(self, region: str, layout: str, n_items: int, seed: int = 0):
        self.args = (region, layout, n_items, seed)

    def __call__(self):
        return make_env(*self.args)


def env_factory(region: str, layout: str, n_items: int, seed: int = 0) -> EnvFactory:
    return EnvFactory(region, layout, n_items, seed)
