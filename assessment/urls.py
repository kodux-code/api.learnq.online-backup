from django.urls import path
from assessment.views import (
    QuestionBankViewSet, AssessmentViewSet, AttemptGradeView,
    AttemptRubricGradeView, PeerReviewViewSet
)

urlpatterns = [
    # Question Bank
    path('questions/', QuestionBankViewSet.as_view(), name='question-list'),
    path('questions/<uuid:pk>/', QuestionBankViewSet.as_view(), name='question-detail'),

    # Assessments
    path('', AssessmentViewSet.as_view(), name='assessment-list'),
    path('<uuid:pk>/', AssessmentViewSet.as_view(), name='assessment-detail'),
    path('<uuid:pk>/publish/', AssessmentViewSet.as_view(), name='assessment-publish'),
    path('<uuid:pk>/duplicate/', AssessmentViewSet.as_view(), name='assessment-duplicate'),
    path('<uuid:pk>/start/', AssessmentViewSet.as_view(), name='assessment-start'),
    path('<uuid:pk>/submit/', AssessmentViewSet.as_view(), name='assessment-submit'),
    path('<uuid:pk>/results/', AssessmentViewSet.as_view(), name='assessment-results'),
    path('<uuid:pk>/my-attempts/', AssessmentViewSet.as_view(), name='assessment-my-attempts'),

    # Attempt grading
    path('attempts/<uuid:pk>/grade/', AttemptGradeView.as_view(), name='attempt-grade'),
    path('attempts/<uuid:pk>/rubric-grade/', AttemptRubricGradeView.as_view(), name='attempt-rubric-grade'),

    # Peer Reviews
    path('peer-reviews/', PeerReviewViewSet.as_view(), name='peer-review-list'),
    path('peer-reviews/<uuid:pk>/start/', PeerReviewViewSet.as_view(), name='peer-review-start'),
    path('peer-reviews/<uuid:pk>/submit/', PeerReviewViewSet.as_view(), name='peer-review-submit'),
]