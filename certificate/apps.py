from django.apps import AppConfig


class CertificateConfig(AppConfig):
    name = 'certificate'

    def ready(self):
        import certificate.signals  # noqa
