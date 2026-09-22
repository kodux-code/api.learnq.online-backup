from django.apps import AppConfig


class EarningConfig(AppConfig):
    name = 'earning'

    def ready(self):
        import earning.signals  # noqa