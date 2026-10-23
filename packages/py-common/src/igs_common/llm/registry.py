"""Role → model id resolution."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from .types import LLMError, Role


class ModelNotConfiguredError(LLMError):
    pass


class ModelRegistry:
    def __init__(self, models: Mapping[Role, str]) -> None:
        self._models = dict(models)

    def model_for(self, role: Role | str) -> str:
        try:
            return self._models[Role(role)]
        except (KeyError, ValueError):
            raise ModelNotConfiguredError(
                f"no model configured for role {role!r}; set IGS_LLM_MODELS"
            ) from None

    def roles(self) -> dict[Role, str]:
        return dict(self._models)

    def missing_from(self, available: Iterable[str]) -> dict[Role, str]:
        """Configured roles whose model id the provider doesn't list."""
        known = set(available)
        return {role: model for role, model in self._models.items() if model not in known}
