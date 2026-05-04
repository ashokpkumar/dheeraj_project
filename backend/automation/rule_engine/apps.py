from django.apps import AppConfig


class RuleEngineConfig(AppConfig):

    name = "rule_engine"

    def ready(self):
        pass
        #TODO remove this incase of new function
        # This forces function registration
        #import rule_engine.functions
