from rest_framework import serializers
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.conf import settings

from client.models import Client, ClientFollow


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
            from account.serializers import StudentAccountSerializer
            return StudentAccountSerializer(obj.student_account).data
        return None

    def get_teacher_account(self, obj):
        if obj.is_teacher and hasattr(obj, 'teacher_account'):
            from account.serializers import TeacherAccountSerializer
            return TeacherAccountSerializer(obj.teacher_account).data
        return None

    def get_moderator_account(self, obj):
        if obj.is_moderator and hasattr(obj, 'moderator_account'):
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
            from client.utils import generate_otp, store_otp, generate_verification_token
            from client.mail import send_templated_email
        except ImportError:
            return

        # Generate and store OTP
        otp = generate_otp()
        store_otp(str(client.id), otp)

        domain = getattr(settings, 'EMAIL_FRONTEND_URL', 'http://localhost:3000').rstrip('/')
        context = {
            "name": client.display_name or client.first_name,
            "otp": otp,
            "domain": domain,
        }
        send_templated_email(
            subject="Your verification code",
            recipient=client.email,
            template_name="emails/verify_email_otp.html",
            context=context,
        )

        # Also send legacy verification link for backward compatibility
        token = generate_verification_token(str(client.id))
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
    full_name = serializers.CharField(source='get_full_name', read_only=True)
    role = serializers.CharField(read_only=True)
    courses_count = serializers.SerializerMethodField()
    reviews_count = serializers.SerializerMethodField()
    followers_count = serializers.SerializerMethodField()
    following_count = serializers.SerializerMethodField()
    is_followed = serializers.SerializerMethodField()
    teacher_account = serializers.SerializerMethodField()

    class Meta:
        model = Client
        fields = [
            'id', 'display_name', 'full_name', 'bio', 'avatar', 'role',
            'courses_count', 'reviews_count',
            'followers_count', 'following_count', 'is_followed',
            'teacher_account', 'created_at'
        ]

    def get_courses_count(self, obj):
        if obj.is_teacher:
            return obj.teacher_courses.filter(is_active=True).count()
        return 0

    def get_reviews_count(self, obj):
        from course.models import Review
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

    def get_teacher_account(self, obj):
        if obj.is_teacher and hasattr(obj, 'teacher_account'):
            from account.serializers import TeacherAccountPublicSerializer
            return TeacherAccountPublicSerializer(obj.teacher_account).data
        return None


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


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)


class PasswordResetConfirmSerializer(serializers.Serializer):
    token = serializers.CharField(required=True)
    password = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'})
    password_confirm = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'})

    def validate(self, attrs):
        if attrs['password'] != attrs['password_confirm']:
            raise serializers.ValidationError({"password_confirm": "Passwords do not match."})
        try:
            validate_password(password=attrs['password'])
        except DjangoValidationError as e:
            raise serializers.ValidationError({"password": list(e.messages)})
        return attrs