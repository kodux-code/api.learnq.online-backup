from django.db import models
from django.db.models.signals import post_save, post_delete, m2m_changed
from django.dispatch import receiver
from django.db.models import Avg, Count

from account.models import TeacherAccount
from .models import Course, Enrollment, Lecture, Review, LectureProgress, CourseTeacher


@receiver(post_save, sender=Enrollment)
def update_course_student_count(sender, instance, created, **kwargs):
    if created:
        Course.objects.filter(pk=instance.course_id).update(total_students=Count('enrollments', filter=models.Q(enrollments__status=Enrollment.Status.ACTIVE)))


@receiver(post_save, sender=Review)
def update_course_rating(sender, instance, **kwargs):
    course = instance.enrollment.course
    stats = Review.objects.filter(enrollment__course=course).aggregate(
        avg_rating=Avg('rating'),
        count=Count('id')
    )
    Course.objects.filter(pk=course.pk).update(
        average_rating=stats['avg_rating'] or 0,
        total_reviews=stats['count'] or 0
    )


@receiver(post_save, sender=LectureProgress)
def update_enrollment_progress(sender, instance, **kwargs):
    if instance.is_completed:
        enrollment = instance.enrollment
        total_lectures = Lecture.objects.filter(section__course=enrollment.course, status=Lecture.Status.PUBLISHED).count()
        completed_count = enrollment.completed_lectures.count()
        if total_lectures > 0:
            progress = round((completed_count / total_lectures) * 100, 2)
            Enrollment.objects.filter(pk=enrollment.pk).update(progress_percentage=progress)
            if progress >= 100 and enrollment.status == Enrollment.Status.ACTIVE:
                Enrollment.objects.filter(pk=enrollment.pk).update(
                    status=Enrollment.Status.COMPLETED,
                    completed_at=models.DateTimeField(auto_now_add=True)
                )


@receiver(m2m_changed, sender=Enrollment.completed_lectures.through)
def update_progress_on_m2m_change(sender, instance, action, **kwargs):
    if action in ['post_add', 'post_remove', 'post_clear']:
        total_lectures = Lecture.objects.filter(section__course=instance.course, status=Lecture.Status.PUBLISHED).count()
        completed_count = instance.completed_lectures.count()
        if total_lectures > 0:
            progress = round((completed_count / total_lectures) * 100, 2)
            Enrollment.objects.filter(pk=instance.pk).update(progress_percentage=progress)


@receiver(post_save, sender=CourseTeacher)
def update_teacher_course_count(sender, instance, created, **kwargs):
    if created and instance.is_active:
        teacher = instance.teacher
        if hasattr(teacher, 'teacher_account'):
            TeacherAccount.objects.filter(pk=teacher.teacher_account.pk).update(
                total_courses=Count('teacher_courses', filter=models.Q(teacher_courses__is_active=True))
            )