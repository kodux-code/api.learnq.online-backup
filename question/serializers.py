from rest_framework import serializers
from django.utils import timezone
from django.conf import settings
from django.db.models import Sum

from client.serializers import MinimalUserSerializer
from .models import Question, Answer, QuestionTag, Vote, QuestionShare, AnswerReport


class QuestionTagSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuestionTag
        fields = ['id', 'name', 'slug', 'description', 'color', 'question_count', 'created_at']
        read_only_fields = ['id', 'question_count', 'created_at']


class QuestionTagListSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuestionTag
        fields = ['id', 'name', 'slug', 'color', 'question_count']


class AuthorSerializer(serializers.ModelSerializer):
    class Meta:
        model = settings.AUTH_USER_MODEL
        fields = ['id', 'display_name', 'avatar']
        read_only_fields = fields


class AnswerSerializer(serializers.ModelSerializer):
    author = AuthorSerializer(read_only=True)
    vote_score = serializers.IntegerField(read_only=True)
    reply_count = serializers.IntegerField(read_only=True)
    replies = serializers.SerializerMethodField()
    can_edit = serializers.SerializerMethodField()
    is_reporter = serializers.SerializerMethodField()

    class Meta:
        model = Answer
        fields = [
            'id', 'question', 'parent', 'author', 'body',
            'is_accepted', 'vote_score', 'reply_count',
            'replies', 'can_edit', 'is_reporter',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'question', 'author', 'is_accepted',
            'vote_score', 'reply_count', 'created_at', 'updated_at',
        ]

    def get_replies(self, obj):
        replies = obj.replies.filter(is_deleted=False).select_related('author').all()
        return AnswerSerializer(replies, many=True, context=self.context).data

    def get_can_edit(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return False
        return request.user.is_staff or obj.author_id == request.user.id

    def get_is_reporter(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return False
        return obj.reports.filter(reporter=request.user).exists()


class AnswerCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Answer
        fields = ['body', 'parent']

    def validate_parent(self, parent):
        question = self.context.get('question')
        if not question:
            question = self.context.get('view').get_question(self.context.get('pk'))
        
        if parent and parent.question_id != question.id:
            raise serializers.ValidationError("The parent answer must belong to this question.")
        return parent

    def validate(self, attrs):
        question = self.context.get('question')
        if not question:
            question = self.context.get('view').get_question(self.context.get('pk'))
        
        if question and not question.is_open:
            raise serializers.ValidationError("This question is closed for answers.")
        
        if question and question.is_deleted:
            raise serializers.ValidationError("This question has been deleted.")
        
        return attrs


class AnswerUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Answer
        fields = ['body']


class QuestionSerializer(serializers.ModelSerializer):
    author = AuthorSerializer(read_only=True)
    tags = QuestionTagListSerializer(many=True, read_only=True)
    vote_score = serializers.IntegerField(read_only=True)
    answer_count = serializers.IntegerField(read_only=True)
    share_count = serializers.IntegerField(read_only=True)
    can_edit = serializers.SerializerMethodField()
    user_vote = serializers.SerializerMethodField()

    class Meta:
        model = Question
        fields = [
            'id', 'author', 'title', 'body', 'tags',
            'is_open', 'is_pinned', 'vote_score',
            'answer_count', 'share_count', 'can_edit',
            'user_vote', 'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'author', 'vote_score', 'answer_count',
            'share_count', 'created_at', 'updated_at',
        ]

    def get_can_edit(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return False
        return request.user.is_staff or obj.author_id == request.user.id

    def get_user_vote(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return None
        vote = obj.votes.filter(voter=request.user).first()
        return vote.value if vote else None


class QuestionDetailSerializer(QuestionSerializer):
    answers = serializers.SerializerMethodField()

    class Meta(QuestionSerializer.Meta):
        fields = QuestionSerializer.Meta.fields + ['answers']

    def get_answers(self, obj):
        root_answers = (
            obj.answers.filter(parent__isnull=True, is_deleted=False)
            .select_related('author')
            .prefetch_related('replies__author')
            .all()
        )
        return AnswerSerializer(root_answers, many=True, context=self.context).data


class QuestionCreateUpdateSerializer(serializers.ModelSerializer):
    tag_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        write_only=True
    )

    class Meta:
        model = Question
        fields = ['title', 'body', 'is_open', 'tag_ids']

    def validate_title(self, value):
        if len(value.strip()) < 5:
            raise serializers.ValidationError("Title must be at least 5 characters.")
        if len(value) > 255:
            raise serializers.ValidationError("Title must not exceed 255 characters.")
        return value.strip()

    def validate_body(self, value):
        if len(value.strip()) < 20:
            raise serializers.ValidationError("Body must be at least 20 characters.")
        return value.strip()

    def create(self, validated_data):
        tag_ids = validated_data.pop('tag_ids', [])
        validated_data['author'] = self.context['request'].user
        question = Question.objects.create(**validated_data)
        if tag_ids:
            question.tags.set(tag_ids)
        return question

    def update(self, instance, validated_data):
        tag_ids = validated_data.pop('tag_ids', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if tag_ids is not None:
            instance.tags.set(tag_ids)
        return instance


class VoteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Vote
        fields = ['value']

    def validate_value(self, value):
        if value not in [Vote.Value.UP, Vote.Value.DOWN]:
            raise serializers.ValidationError("Vote value must be 1 or -1.")
        return value


class QuestionShareSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuestionShare
        fields = ['channel']

    def create(self, validated_data):
        validated_data['question'] = self.context['question']
        validated_data['shared_by'] = self.context['request'].user
        return super().create(validated_data)


class QuestionShareListSerializer(serializers.ModelSerializer):
    shared_by = AuthorSerializer(read_only=True)
    
    class Meta:
        model = QuestionShare
        fields = ['id', 'channel', 'shared_by', 'created_at']
        read_only_fields = fields


class AnswerReportSerializer(serializers.ModelSerializer):
    reporter = AuthorSerializer(read_only=True)
    resolved_by = AuthorSerializer(read_only=True)

    class Meta:
        model = AnswerReport
        fields = [
            'id', 'answer', 'reporter', 'reason', 'details',
            'is_resolved', 'resolved_by', 'resolved_at', 'created_at'
        ]
        read_only_fields = ['id', 'reporter', 'is_resolved', 'resolved_by', 'resolved_at', 'created_at']


class AnswerReportCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = AnswerReport
        fields = ['answer', 'reason', 'details']

    def validate(self, attrs):
        request = self.context.get('request')
        answer = attrs.get('answer')
        
        if AnswerReport.objects.filter(answer=answer, reporter=request.user).exists():
            raise serializers.ValidationError("You have already reported this answer.")
        
        if answer.author == request.user:
            raise serializers.ValidationError("You cannot report your own answer.")
        
        return attrs

    def create(self, validated_data):
        validated_data['reporter'] = self.context['request'].user
        return super().create(validated_data)


class AnswerReportResolveSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=['resolve', 'dismiss'])
    resolution_note = serializers.CharField(required=False, allow_blank=True)