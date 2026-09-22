from django.apps import AppConfig


class QuestionConfig(AppConfig):
    name = 'question'
    verbose_name = 'Questions & Answers'

    def ready(self):
        import question.signals  # noqa