from django.urls import path
from .views import (
    QuestionTagListView, QuestionListCreateView, QuestionDetailView, QuestionActionView,
    QuestionAnswerListCreateView, AnswerDetailView, AnswerActionView,
    VoteView, QuestionShareView, AnswerReportView, QuestionShareListView
)

urlpatterns = [
    # Tags
    path('tags/', QuestionTagListView.as_view(), name='question-tag-list'),

    # Questions
    path('', QuestionListCreateView.as_view(), name='question-list-create'),
    path('<uuid:pk>/', QuestionDetailView.as_view(), name='question-detail'),
    path('<uuid:pk>/action/', QuestionActionView.as_view(), name='question-action'),

    # Answers
    path('<uuid:pk>/answers/', QuestionAnswerListCreateView.as_view(), name='question-answer-list-create'),
    path('answers/<uuid:pk>/', AnswerDetailView.as_view(), name='answer-detail'),
    path('answers/<uuid:pk>/action/', AnswerActionView.as_view(), name='answer-action'),

    # Voting
    path('<uuid:pk>/vote/', VoteView.as_view(), name='question-vote'),
    path('answers/<uuid:pk>/vote/', VoteView.as_view(), name='answer-vote'),

    # Sharing
    path('<uuid:pk>/share/', QuestionShareView.as_view(), name='question-share'),
    path('<uuid:pk>/shares/', QuestionShareListView.as_view(), name='question-shares'),

    # Reports
    path('answers/<uuid:pk>/report/', AnswerReportView.as_view(), name='answer-report'),
    path('reports/', AnswerReportView.as_view(), name='answer-report-list'),
]