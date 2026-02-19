from django.apps import AppConfig


class RuleEngineConfig(AppConfig):

    name = "rule_engine"

    def ready(self):

        # This forces function registration
        import rule_engine.functions
