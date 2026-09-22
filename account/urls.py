from django.urls import path
from .views import (
    StudentAccountView, TeacherAccountView, TeacherPublicProfileView,
    TeacherListView, ModeratorAccountView, CurrentUserAccountView,
    TeacherStatsView, TeacherEarningsView
)

urlpatterns = [
    path('me/', CurrentUserAccountView.as_view(), name='current-user-account'),
    path('student/', StudentAccountView.as_view(), name='student-account'),
    path('teacher/', TeacherAccountView.as_view(), name='teacher-account'),
    path('teacher/stats/', TeacherStatsView.as_view(), name='teacher-stats'),
    path('teacher/earnings/', TeacherEarningsView.as_view(), name='teacher-earnings'),
    path('moderator/', ModeratorAccountView.as_view(), name='moderator-account'),
    path('teachers/', TeacherListView.as_view(), name='teacher-list'),
    path('teachers/<uuid:teacher_id>/', TeacherPublicProfileView.as_view(), name='teacher-public-profile'),
]