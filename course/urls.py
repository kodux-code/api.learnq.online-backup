from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    CategoryViewSet, CourseViewSet, SectionViewSet, LectureViewSet,
    EnrollmentViewSet, ReviewViewSet, QuestionViewSet, AnswerViewSet,
    LectureProgressViewSet, CourseAttachmentViewSet
)

router = DefaultRouter()
router.register(r'categories', CategoryViewSet, basename='category')
router.register(r'courses', CourseViewSet, basename='course')
router.register(r'enrollments', EnrollmentViewSet, basename='enrollment')
router.register(r'reviews', ReviewViewSet, basename='review')
router.register(r'questions', QuestionViewSet, basename='question')
router.register(r'answers', AnswerViewSet, basename='answer')
router.register(r'progress', LectureProgressViewSet, basename='lecture-progress')
router.register(r'attachments', CourseAttachmentViewSet, basename='attachment')

urlpatterns = [
    path('courses/<uuid:course_pk>/sections/', SectionViewSet.as_view({'get': 'list', 'post': 'create'}), name='section-list'),
    path('courses/<uuid:course_pk>/sections/<uuid:pk>/', SectionViewSet.as_view({'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy'}), name='section-detail'),
    path('courses/<uuid:course_pk>/sections/<uuid:pk>/reorder/', SectionViewSet.as_view({'post': 'reorder'}), name='section-reorder'),

    path('courses/<uuid:course_pk>/sections/<uuid:section_pk>/lectures/', LectureViewSet.as_view({'get': 'list', 'post': 'create'}), name='lecture-list'),
    path('courses/<uuid:course_pk>/sections/<uuid:section_pk>/lectures/<uuid:pk>/', LectureViewSet.as_view({'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy'}), name='lecture-detail'),
    path('courses/<uuid:course_pk>/sections/<uuid:section_pk>/lectures/<uuid:pk>/reorder/', LectureViewSet.as_view({'post': 'reorder'}), name='lecture-reorder'),

    path('courses/<uuid:course_pk>/announcements/', CourseViewSet.as_view({'get': 'announcements', 'post': 'announcements'}), name='course-announcements'),
    path('courses/<uuid:course_pk>/questions/', CourseViewSet.as_view({'get': 'questions', 'post': 'questions'}), name='course-questions'),
    path('courses/<uuid:course_pk>/reviews/', CourseViewSet.as_view({'get': 'reviews'}), name='course-reviews'),
    path('courses/<uuid:course_pk>/enroll/', CourseViewSet.as_view({'post': 'enroll'}), name='course-enroll'),
    path('courses/<uuid:course_pk>/progress/', CourseViewSet.as_view({'get': 'progress'}), name='course-progress'),
    path('courses/<uuid:course_pk>/lectures/<uuid:lecture_id>/complete/', CourseViewSet.as_view({'post': 'complete_lecture'}), name='lecture-complete'),

    path('courses/<uuid:course_pk>/questions/<uuid:question_pk>/answers/', AnswerViewSet.as_view({'get': 'list', 'post': 'create'}), name='answer-list'),
    path('courses/<uuid:course_pk>/questions/<uuid:question_pk>/answers/<uuid:pk>/', AnswerViewSet.as_view({'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy'}), name='answer-detail'),
    path('courses/<uuid:course_pk>/questions/<uuid:question_pk>/answers/<uuid:pk>/accept/', AnswerViewSet.as_view({'post': 'accept'}), name='answer-accept'),

    path('enrollments/<uuid:enrollment_pk>/progress/', LectureProgressViewSet.as_view({'get': 'list', 'post': 'create'}), name='enrollment-progress-list'),
    path('enrollments/<uuid:enrollment_pk>/progress/<uuid:pk>/', LectureProgressViewSet.as_view({'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy'}), name='enrollment-progress-detail'),

    path('courses/<uuid:course_pk>/attachments/', CourseAttachmentViewSet.as_view({'get': 'list', 'post': 'create'}), name='attachment-list'),
    path('courses/<uuid:course_pk>/attachments/<uuid:pk>/', CourseAttachmentViewSet.as_view({'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy'}), name='attachment-detail'),
]