from rest_framework import serializers
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.conf import settings
from client.models import Client, ClientFollow


class MinimalUserSerializer(serializers.ModelSerializer):
    avatar = serializers.ImageField(read_only=True, allow_null=True)

    class Meta:
        model = Client
        fields = ['id', 'display_name', 'avatar']
        read_only_fields = fields

class ClientSerializer(serializers.ModelSerializer):
    role = serializers.ChoiceField(choices=Client.Role.choices, read_only=True)
    full_name = serializers.CharField(source='get_full_name', read_only=True)
    student_account = serializers.SerializerMethodField()
    teacher_account = serializers.SerializerMethodField()
    moderator_account = serializers.SerializerMethodField()

    class Meta:
        model = Client
        fields = [
            'id', 'first_name', 'last_name', 'display_name', 'email',
            'role', 'bio', 'avatar', 'full_name',
            'is_active', 'is_verified', 'is_staff',
            'student_account', 'teacher_account', 'moderator_account',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'role', 'is_active', 'is_verified', 'is_staff', 'created_at', 'updated_at']

    def get_student_account(self, obj):
        if obj.is_student and hasattr(obj, 'student_account'):
            from account.models import StudentAccount
            from account.serializers import StudentAccountSerializer
            return StudentAccountSerializer(obj.student_account).data
        return None

    def get_teacher_account(self, obj):
        if obj.is_teacher and hasattr(obj, 'teacher_account'):
            from account.models import TeacherAccount
            from account.serializers import TeacherAccountSerializer
            return TeacherAccountSerializer(obj.teacher_account).data
        return None

    def get_moderator_account(self, obj):
        if obj.is_moderator and hasattr(obj, 'moderator_account'):
            from account.models import ModeratorAccount
            from account.serializers import ModeratorAccountSerializer
            return ModeratorAccountSerializer(obj.moderator_account).data
        return None


class ClientRegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, style={'input_type': 'password'})
    password_confirm = serializers.CharField(write_only=True, style={'input_type': 'password'})

    class Meta:
        model = Client
        fields = ['id', 'first_name', 'last_name', 'display_name', 'email', 'password', 'password_confirm', 'role']
        read_only_fields = ['id']

    def validate_display_name(self, value):
        if Client.objects.filter(display_name__iexact=value).exists():
            raise serializers.ValidationError("This display name is already taken.")
        return value

    def validate_email(self, value):
        if Client.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return value.lower()

    def validate(self, attrs):
        if attrs['password'] != attrs['password_confirm']:
            raise serializers.ValidationError({"password_confirm": "Passwords do not match."})
        try:
            validate_password(password=attrs['password'])
        except DjangoValidationError as e:
            raise serializers.ValidationError({"password": list(e.messages)})
        return attrs

    def create(self, validated_data):
        validated_data.pop('password_confirm')
        with transaction.atomic():
            client = Client.objects.create_user(**validated_data)
            self.send_verification_email(client)
        return client

    def send_verification_email(self, client):
        try:
            from client.utils import generate_verification_token
            from client.mail import send_templated_email
        except ImportError:
            return

        token = generate_verification_token(client.id)
        domain = getattr(settings, 'EMAIL_FRONTEND_URL', 'http://localhost:3000').rstrip('/')
        verification_url = f"{domain}/auth/verify-email?token={token}"
        context = {
            "name": client.display_name or client.first_name,
            "verification_url": verification_url
        }
        send_templated_email(
            subject="Verify your registration",
            recipient=client.email,
            template_name="emails/verify_email.html",
            context=context,
        )


class ClientUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Client
        fields = ['first_name', 'last_name', 'display_name', 'bio', 'avatar']

    def validate_display_name(self, value):
        if Client.objects.filter(display_name__iexact=value).exclude(pk=self.instance.pk).exists():
            raise serializers.ValidationError("This display name is already taken.")
        return value


class PublicProfileSerializer(serializers.ModelSerializer):
    """
    Base public profile serializer - includes common fields for all roles.
    Role-specific data is added via role-specific serializers.
    """
    full_name = serializers.CharField(source='get_full_name', read_only=True)
    role = serializers.CharField(read_only=True)
    is_verified = serializers.BooleanField(read_only=True)
    courses_count = serializers.SerializerMethodField()
    reviews_count = serializers.SerializerMethodField()
    followers_count = serializers.SerializerMethodField()
    following_count = serializers.SerializerMethodField()
    is_followed = serializers.SerializerMethodField()
    joined_date = serializers.SerializerMethodField()
    
    # Role-specific account data
    student_account = serializers.SerializerMethodField()
    teacher_account = serializers.SerializerMethodField()
    moderator_account = serializers.SerializerMethodField()

    class Meta:
        model = Client
        fields = [
            'id', 'display_name', 'full_name', 'bio', 'avatar', 'role',
            'is_verified', 'joined_date',
            'courses_count', 'reviews_count',
            'followers_count', 'following_count', 'is_followed',
            'student_account', 'teacher_account', 'moderator_account',
        ]

    def get_courses_count(self, obj):
        if obj.is_teacher:
            from course.models import Course
            return Course.objects.filter(
                course_teachers__teacher=obj,
                course_teachers__is_active=True,
                status=Course.Status.PUBLISHED
            ).count()
        if obj.is_student:
            from course.models import Enrollment
            return Enrollment.objects.filter(
                student=obj, 
                status=Enrollment.Status.ACTIVE
            ).count()
        return 0

    def get_reviews_count(self, obj):
        from course.models import Review
        if obj.is_teacher:
            return Review.objects.filter(
                enrollment__course__course_teachers__teacher=obj,
                enrollment__course__course_teachers__is_active=True
            ).count()
        return Review.objects.filter(enrollment__student=obj).count()

    def get_followers_count(self, obj):
        return obj.follower_relationships.count()

    def get_following_count(self, obj):
        return obj.following_relationships.count()

    def get_is_followed(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return False
        if hasattr(obj, 'followed_by_current_user'):
            return obj.followed_by_current_user
        return ClientFollow.objects.filter(follower=request.user, following=obj).exists()

    def get_joined_date(self, obj):
        return obj.created_at.strftime('%B %Y')

    def get_student_account(self, obj):
        if obj.is_student and hasattr(obj, 'student_account'):
            from account.serializers import StudentAccountSerializer
            return StudentAccountSerializer(obj.student_account, context=self.context).data
        return None

    def get_teacher_account(self, obj):
        if obj.is_teacher and hasattr(obj, 'teacher_account'):
            from account.serializers import TeacherAccountPublicSerializer
            return TeacherAccountPublicSerializer(obj.teacher_account, context=self.context).data
        return None

    def get_moderator_account(self, obj):
        if obj.is_moderator and hasattr(obj, 'moderator_account'):
            from account.serializers import ModeratorAccountSerializer
            return ModeratorAccountSerializer(obj.moderator_account, context=self.context).data
        return None


class StudentPublicProfileSerializer(PublicProfileSerializer):
    """Extended serializer for student profiles with additional student-specific fields."""
    
    class Meta(PublicProfileSerializer.Meta):
        fields = PublicProfileSerializer.Meta.fields + [
            'grade_level', 'credits_earned', 'completed_courses_count',
        ]
    
    grade_level = serializers.CharField(source='student_account.grade_level', read_only=True)
    credits_earned = serializers.IntegerField(source='student_account.credits_earned', read_only=True)
    completed_courses_count = serializers.SerializerMethodField()
    
    def get_completed_courses_count(self, obj):
        if obj.is_student:
            from course.models import Enrollment
            return Enrollment.objects.filter(
                student=obj, 
                status=Enrollment.Status.COMPLETED
            ).count()
        return 0


class TeacherPublicProfileSerializer(PublicProfileSerializer):
    """Extended serializer for teacher profiles with additional teacher-specific fields."""
    
    class Meta(PublicProfileSerializer.Meta):
        fields = PublicProfileSerializer.Meta.fields + [
            'total_students', 'total_courses', 'average_rating', 'rating', 'review_count',
            'hourly_rate', 'currency', 'qualifications',
        ]
    
    total_students = serializers.IntegerField(source='teacher_account.total_students', read_only=True)
    total_courses = serializers.IntegerField(source='teacher_account.total_courses', read_only=True)
    average_rating = serializers.DecimalField(source='teacher_account.average_rating', max_digits=3, decimal_places=2, read_only=True)
    rating = serializers.DecimalField(source='teacher_account.rating', max_digits=3, decimal_places=2, read_only=True)
    review_count = serializers.IntegerField(source='teacher_account.review_count', read_only=True)
    hourly_rate = serializers.DecimalField(source='teacher_account.hourly_rate', max_digits=10, decimal_places=2, read_only=True)
    currency = serializers.CharField(source='teacher_account.currency', read_only=True)
    qualifications = serializers.CharField(source='teacher_account.qualifications', read_only=True)


class ModeratorPublicProfileSerializer(PublicProfileSerializer):
    """Extended serializer for moderator profiles with additional moderator-specific fields."""
    
    class Meta(PublicProfileSerializer.Meta):
        fields = PublicProfileSerializer.Meta.fields + [
            'department', 'is_senior', 'actions_taken', 'last_action_at',
        ]
    
    department = serializers.CharField(source='moderator_account.department', read_only=True)
    is_senior = serializers.BooleanField(source='moderator_account.is_senior', read_only=True)
    actions_taken = serializers.IntegerField(source='moderator_account.actions_taken', read_only=True)
    last_action_at = serializers.DateTimeField(source='moderator_account.last_action_at', read_only=True)


class ClientFollowSerializer(serializers.ModelSerializer):
    follower = PublicProfileSerializer(read_only=True)
    following = PublicProfileSerializer(read_only=True)
    follower_id = serializers.UUIDField(write_only=True)
    following_id = serializers.UUIDField(write_only=True)

    class Meta:
        model = ClientFollow
        fields = ['id', 'follower', 'following', 'follower_id', 'following_id', 'created_at']
        read_only_fields = ['id', 'follower', 'following', 'created_at']

    def validate(self, attrs):
        follower_id = attrs.get('follower_id')
        following_id = attrs.get('following_id')

        if follower_id == following_id:
            raise serializers.ValidationError("You cannot follow yourself.")

        if not Client.objects.filter(id=following_id).exists():
            raise serializers.ValidationError({"following_id": "User not found."})

        if ClientFollow.objects.filter(follower_id=follower_id, following_id=following_id).exists():
            raise serializers.ValidationError("Already following this user.")

        return attrs

    def create(self, validated_data):
        follower = Client.objects.get(id=validated_data.pop('follower_id'))
        following = Client.objects.get(id=validated_data.pop('following_id'))
        return ClientFollow.objects.create(follower=follower, following=following)


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(required=True, style={'input_type': 'password'})
    new_password = serializers.CharField(required=True, style={'input_type': 'password'})
    new_password_confirm = serializers.CharField(required=True, style={'input_type': 'password'})

    def validate_new_password(self, value):
        try:
            validate_password(value)
        except DjangoValidationError as e:
            raise serializers.ValidationError(list(e.messages))
        return value

    def validate(self, attrs):
        if attrs['new_password'] != attrs['new_password_confirm']:
            raise serializers.ValidationError({"new_password_confirm": "Passwords do not match."})
        return attrs

    def save(self, **kwargs):
        user = self.context['request'].user
        if not user.check_password(self.validated_data['old_password']):
            raise serializers.ValidationError({"old_password": "Current password is incorrect."})
        user.set_password(self.validated_data['new_password'])
        user.save()
        return user