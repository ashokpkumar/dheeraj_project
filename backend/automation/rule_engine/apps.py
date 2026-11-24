import logging

from django.apps import AppConfig


logger = logging.getLogger(__name__)


class RuleEngineConfig(AppConfig):

    name = "rule_engine"

    def ready(self):
        # Importing the functions package runs all @register_function
        # decorators, which only populate the in-memory FUNCTION_REGISTRY.
        # No database access happens here, so this is safe to run during
        # app loading. Use the "Refresh functions" action (refresh_functions
        # view) to sync the registry to the database once the app is up.
        try:
            import rule_engine.functions  # noqa: F401
            from .registry import FUNCTION_REGISTRY
            logger.info("rule_engine ready: %s function(s) registered", len(FUNCTION_REGISTRY),
                        extra={"event_name": "app_ready", "function_count": len(FUNCTION_REGISTRY)})
        except Exception:
            # Make sure failures are visible at startup instead of failing
            # silently (or only as a truncated warning).
            logger.exception("Failed to load rule_engine.functions during startup")
            raise
