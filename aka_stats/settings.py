import os
from typing import Set
from warnings import warn

ENV_PREFIX = "AKA_STATS"


class Settings:
    @property
    def default_prefix(self):
        """Backward compatibility, use 'namespace' value now."""
        warn(
            DeprecationWarning(
                "aka_stats.settings:Settings.default_prefix is deprecated, please use Settings.namespace"
            )
        )
        return self.namespace

    @default_prefix.setter
    def default_prefix_setter(self, value: str):
        """Backward compatibility, use 'namespace' value now."""
        warn(
            DeprecationWarning(
                "aka_stats.settings:Settings.default_prefix is deprecated, please use Settings.namespace"
            )
        )
        self.namespace = value

    history_size: int = int(os.getenv(f"{ENV_PREFIX}_HISTORY_SIZE", 1000))
    timezone: str = os.getenv(f"{ENV_PREFIX}_TIMEZONE", "Europe/London")
    # AKA_STATS_DEFAULT_PREFIX kept for backward compatibility
    namespace: str = os.getenv(f"{ENV_PREFIX}_NAMESPACE", os.getenv(f"{ENV_PREFIX}_DEFAULT_PREFIX", "AKA-STATS"))

    redis_url: str = os.getenv(f"{ENV_PREFIX}_REDIS_URL", "redis://127.0.0.1:6379")

    config_options: Set[str] = {"history_size", "timezone", "namespace", "redis_url"}

    def __str__(self) -> str:
        return "\n".join([f"{ENV_PREFIX}_{opt.upper()} = {getattr(self, opt)}" for opt in self.config_options])


config = Settings()
