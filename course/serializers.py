from django.utils import timezone
from rest_framework import serializers
from .models import (
    Category, Course, CourseTeacher, Section, Lecture,
    Enrollment, Review, Announcement, Question, Answer,
    LectureProgress, CourseAttachment
)
from client.models import Client


class CategorySerializer(serializers.ModelSerializer):
    children = serializers.SerializerMethodField()
    course_count = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = ['id', 'name', 'slug', 'description', 'icon', 'parent', 'order', 'is_active', 'children', 'course_count']

    def get_children(self, obj):
        children = obj.children.filter(is_active=True)
        return CategorySerializer(children, many=True).data

    def get_course_count(self, obj):
        return Course.objects.filter(category=obj, status=Course.Status.PUBLISHED).count()


class TeacherMinimalSerializer(serializers.ModelSerializer):
    teacher_account = serializers.SerializerMethodField()

    class Meta:
        model = Client
        fields = ['id', 'display_name', 'avatar', 'teacher_account']

    def get_teacher_account(self, obj):
        if hasattr(obj, 'teacher_account'):
            ta = obj.teacher_account
            return {
                'rating': float(ta.rating),
                'review_count': ta.review_count,
                'total_students': ta.total_students,
                'total_courses': ta.total_courses,
            }
        return None


class CourseTeacherSerializer(serializers.ModelSerializer):
    teacher = TeacherMinimalSerializer(read_only=True)
    teacher_id = serializers.UUIDField(write_only=True)

    class Meta:
        model = CourseTeacher
        fields = ['id', 'teacher', 'teacher_id', 'role', 'revenue_share', 'joined_at', 'is_active']
        read_only_fields = ['id', 'joined_at']


class LectureSerializer(serializers.ModelSerializer):
    is_completed = serializers.SerializerMethodField()
    watch_time = serializers.SerializerMethodField()
    last_position = serializers.SerializerMethodField()

    class Meta:
        model = Lecture
        fields = [
            'id', 'title', 'description', 'type', 'status', 'video_url', 'video_duration',
            'video_provider', 'content', 'passing_score', 'max_attempts', 'order',
            'is_free_preview', 'is_downloadable', 'resources', 'created_at', 'updated_at',
            'is_completed', 'watch_time', 'last_position'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_is_completed(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            enrollment = Enrollment.objects.filter(
                student=request.user, course=obj.section.course, status=Enrollment.Status.ACTIVE
            ).first()
            if enrollment:
                return obj.progress_records.filter(enrollment=enrollment, is_completed=True).exists()
        return False

    def get_watch_time(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            enrollment = Enrollment.objects.filter(
                student=request.user, course=obj.section.course, status=Enrollment.Status.ACTIVE
            ).first()
            if enrollment:
                progress = obj.progress_records.filter(enrollment=enrollment).first()
                return progress.watch_time if progress else 0
        return 0

    def get_last_position(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            enrollment = Enrollment.objects.filter(
                student=request.user, course=obj.section.course, status=Enrollment.Status.ACTIVE
            ).first()
            if enrollment:
                progress = obj.progress_records.filter(enrollment=enrollment).first()
                return progress.last_position if progress else 0
        return 0


class SectionSerializer(serializers.ModelSerializer):
    lectures = LectureSerializer(many=True, read_only=True)
    lecture_count = serializers.IntegerField(read_only=True)
    total_duration = serializers.IntegerField(read_only=True)

    class Meta:
        model = Section
        fields = ['id', 'title', 'description', 'order', 'is_free_preview', 'created_at', 'updated_at', 'lectures', 'lecture_count', 'total_duration']


class CourseListSerializer(serializers.ModelSerializer):
    category = CategorySerializer(read_only=True)
    teachers = CourseTeacherSerializer(source='course_teachers', many=True, read_only=True)
    primary_teacher = serializers.SerializerMethodField()
    is_enrolled = serializers.SerializerMethodField()
    progress = serializers.SerializerMethodField()

    class Meta:
        model = Course
        fields = [
            'id', 'title', 'slug', 'subtitle', 'description', 'thumbnail', 'preview_video',
            'category', 'level', 'language', 'price', 'sale_price', 'is_free', 'current_price',
            'discount_percentage', 'status', 'total_students', 'total_reviews', 'average_rating',
            'total_duration_minutes', 'total_lectures', 'teachers', 'primary_teacher',
            'is_enrolled', 'progress', 'created_at', 'published_at'
        ]

    def get_primary_teacher(self, obj):
        primary = obj.course_teachers.filter(role=CourseTeacher.Role.PRIMARY, is_active=True).first()
        if primary:
            return TeacherMinimalSerializer(primary.teacher).data
        first = obj.course_teachers.filter(is_active=True).first()
        return TeacherMinimalSerializer(first.teacher).data if first else None

    def get_is_enrolled(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return Enrollment.objects.filter(
                student=request.user, course=obj, status=Enrollment.Status.ACTIVE
            ).exists()
        return False

    def get_progress(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            enrollment = Enrollment.objects.filter(
                student=request.user, course=obj, status=Enrollment.Status.ACTIVE
            ).first()
            return float(enrollment.progress_percentage) if enrollment else 0
        return 0


class CourseDetailSerializer(CourseListSerializer):
    sections = SectionSerializer(many=True, read_only=True)
    requirements = serializers.JSONField()
    learning_outcomes = serializers.JSONField()
    target_audience = serializers.JSONField()
    caption_languages = serializers.JSONField()

    class Meta(CourseListSerializer.Meta):
        fields = CourseListSerializer.Meta.fields + [
            'sections', 'requirements', 'learning_outcomes', 'target_audience',
            'caption_languages', 'meta_title', 'meta_description'
        ]

class CourseCreateUpdateSerializer(serializers.ModelSerializer):
    course_teachers = CourseTeacherSerializer(many=True, required=False)
    requirements = serializers.JSONField(required=False, default=list)
    learning_outcomes = serializers.JSONField(required=False, default=list)
    target_audience = serializers.JSONField(required=False, default=list)
    caption_languages = serializers.JSONField(required=False, default=list)

    class Meta:
        model = Course
        fields = [
            'id', 'title', 'subtitle', 'description', 'thumbnail', 'preview_video',
            'category', 'subcategory', 'level', 'language', 'caption_languages',
            'price', 'sale_price', 'is_free', 'status', 'requirements',
            'learning_outcomes', 'target_audience', 'meta_title', 'meta_description',
            'course_teachers'
        ]
        read_only_fields = ['id', 'slug', 'total_students', 'total_reviews', 'average_rating',
                           'total_duration_minutes', 'total_lectures', 'created_at', 'updated_at']

    def validate(self, attrs):
        if attrs.get('sale_price') and attrs.get('price'):
            if attrs['sale_price'] >= attrs['price']:
                raise serializers.ValidationError("Sale price must be less than regular price.")
        if attrs.get('is_free') and (attrs.get('price', 0) > 0 or attrs.get('sale_price')):
            raise serializers.ValidationError("Free courses cannot have a price.")
        return attrs

    def create(self, validated_data):
        teachers_data = validated_data.pop('course_teachers', [])
        course = Course.objects.create(**validated_data)
        for teacher_data in teachers_data:
            CourseTeacher.objects.create(course=course, **teacher_data)
        return course

    def update(self, instance, validated_data):
        teachers_data = validated_data.pop('course_teachers', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        
        if teachers_data is not None:
            instance.course_teachers.all().delete()
            for teacher_data in teachers_data:
                CourseTeacher.objects.create(course=instance, **teacher_data)
        return instance


class SectionCreateUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Section
        fields = ['id', 'title', 'description', 'order', 'is_free_preview']
        read_only_fields = ['id']


class LectureCreateUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Lecture
        fields = [
            'id', 'section', 'title', 'description', 'type', 'status',
            'video_url', 'video_duration', 'video_provider', 'content',
            'passing_score', 'max_attempts', 'order', 'is_free_preview',
            'is_downloadable', 'resources'
        ]
        read_only_fields = ['id']


class EnrollmentSerializer(serializers.ModelSerializer):
    course = CourseListSerializer(read_only=True)
    course_id = serializers.UUIDField(write_only=True)
    can_review = serializers.SerializerMethodField()

    class Meta:
        model = Enrollment
        fields = [
            'id', 'course', 'course_id', 'status', 'progress_percentage',
            'amount_paid', 'currency', 'payment_id', 'enrolled_at',
            'completed_at', 'certificate_issued', 'certificate_id',
            'certificate_issued_at', 'has_reviewed', 'can_review'
        ]
        read_only_fields = ['id', 'status', 'progress_percentage', 'amount_paid',
                           'currency', 'payment_id', 'enrolled_at', 'completed_at',
                           'certificate_issued', 'certificate_id', 'certificate_issued_at',
                           'has_reviewed']

    def get_can_review(self, obj):
        return obj.status == Enrollment.Status.ACTIVE and not obj.has_reviewed


class EnrollmentCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Enrollment
        fields = ['course_id', 'amount_paid', 'currency', 'payment_id']
        read_only_fields = ['amount_paid', 'currency', 'payment_id']

    def validate_course_id(self, value):
        try:
            course = Course.objects.get(pk=value, status=Course.Status.PUBLISHED)
        except Course.DoesNotExist:
            raise serializers.ValidationError("Course not found or not published.")
        return value

    def create(self, validated_data):
        validated_data['student'] = self.context['request'].user
        course = Course.objects.get(pk=validated_data['course_id'])
        if course.is_free:
            validated_data['amount_paid'] = 0
            validated_data['currency'] = 'USD'
        return super().create(validated_data)


class ReviewSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='enrollment.student.display_name', read_only=True)
    student_avatar = serializers.ImageField(source='enrollment.student.avatar', read_only=True)
    course_title = serializers.CharField(source='enrollment.course.title', read_only=True)

    class Meta:
        model = Review
        fields = [
            'id', 'enrollment', 'rating', 'title', 'content',
            'content_quality', 'instructor_skill', 'course_value',
            'is_verified', 'helpful_count', 'instructor_response',
            'instructor_responded_at', 'student_name', 'student_avatar',
            'course_title', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'enrollment', 'is_verified', 'helpful_count',
                           'instructor_response', 'instructor_responded_at',
                           'created_at', 'updated_at']


class ReviewCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Review
        fields = ['enrollment', 'rating', 'title', 'content', 'content_quality', 'instructor_skill', 'course_value']

    def validate_enrollment(self, value):
        request = self.context['request']
        if value.student != request.user:
            raise serializers.ValidationError("You can only review your own enrollments.")
        if value.has_reviewed:
            raise serializers.ValidationError("You have already reviewed this course.")
        if value.status != Enrollment.Status.ACTIVE and value.status != Enrollment.Status.COMPLETED:
            raise serializers.ValidationError("You can only review active or completed enrollments.")
        return value


class AnnouncementSerializer(serializers.ModelSerializer):
    teacher_name = serializers.CharField(source='teacher.display_name', read_only=True)

    class Meta:
        model = Announcement
        fields = ['id', 'course', 'teacher', 'teacher_name', 'title', 'content', 'is_published', 'send_email', 'created_at', 'updated_at']
        read_only_fields = ['id', 'teacher', 'created_at', 'updated_at']


class AnswerSerializer(serializers.ModelSerializer):
    teacher = TeacherMinimalSerializer(read_only=True)
    teacher_id = serializers.UUIDField(write_only=True)

    class Meta:
        model = Answer
        fields = ['id', 'question', 'teacher', 'teacher_id', 'content', 'is_accepted', 'upvotes', 'downvotes', 'created_at', 'updated_at']
        read_only_fields = ['id', 'teacher', 'upvotes', 'downvotes', 'created_at', 'updated_at']


class QuestionSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.display_name', read_only=True)
    student_avatar = serializers.ImageField(source='student.avatar', read_only=True)
    answers = AnswerSerializer(many=True, read_only=True)
    answer_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Question
        fields = ['id', 'lecture', 'course', 'student', 'student_name', 'student_avatar', 'title', 'content', 'is_answered', 'is_pinned', 'upvotes', 'downvotes', 'answers', 'answer_count', 'created_at', 'updated_at']
        read_only_fields = ['id', 'student', 'is_answered', 'upvotes', 'downvotes', 'created_at', 'updated_at']


class QuestionCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Question
        fields = ['lecture', 'course', 'title', 'content']

    def validate(self, attrs):
        lecture = attrs.get('lecture')
        course = attrs.get('course')
        if lecture and lecture.section.course != course:
            raise serializers.ValidationError("Lecture does not belong to this course.")
        if not lecture and not course:
            raise serializers.ValidationError("Either lecture or course must be provided.")
        return attrs


class LectureProgressSerializer(serializers.ModelSerializer):
    class Meta:
        model = LectureProgress
        fields = ['id', 'enrollment', 'lecture', 'watch_time', 'is_completed', 'completed_at', 'last_position', 'created_at', 'updated_at']
        read_only_fields = ['id', 'enrollment', 'completed_at', 'created_at', 'updated_at']


class LectureProgressUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = LectureProgress
        fields = ['watch_time', 'is_completed', 'last_position']

    def update(self, instance, validated_data):
        if validated_data.get('is_completed') and not instance.is_completed:
            validated_data['completed_at'] = timezone.now()
        return super().update(instance, validated_data)


class CourseAttachmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = CourseAttachment
        fields = ['id', 'course', 'lecture', 'title', 'file', 'file_size', 'file_type', 'is_downloadable', 'order', 'created_at']
        read_only_fields = ['id', 'file_size', 'file_type', 'created_at']


class CourseStatsSerializer(serializers.Serializer):
    total_courses = serializers.IntegerField()
    published_courses = serializers.IntegerField()
    draft_courses = serializers.IntegerField()
    total_students = serializers.IntegerField()
    total_revenue = serializers.DecimalField(max_digits=12, decimal_places=2)
    average_rating = serializers.DecimalField(max_digits=3, decimal_places=2)
