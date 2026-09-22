from django.apps import AppConfig


class AnalyticConfig(AppConfig):
    name = 'analytic'

    def ready(self):
        import analytic.signals  # noqa