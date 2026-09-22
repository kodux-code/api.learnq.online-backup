from django.shortcuts import get_object_or_404
from django.db.models import Q
from django.utils import timezone
import uuid
from rest_framework.decorators import action
from rest_framework import status, filters
from rest_framework.permissions import AllowAny, IsAuthenticated, IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.generics import ListAPIView, RetrieveAPIView, GenericAPIView
from rest_framework.pagination import PageNumberPagination

from .models import Answer, Question, QuestionTag, Vote, QuestionShare, AnswerReport
from .serializers import (
    AnswerSerializer, AnswerCreateSerializer, AnswerUpdateSerializer,
    QuestionSerializer, QuestionDetailSerializer, QuestionCreateUpdateSerializer,
    QuestionShareSerializer, QuestionShareListSerializer,
    VoteSerializer, AnswerReportSerializer, AnswerReportCreateSerializer,
    AnswerReportResolveSerializer, QuestionTagListSerializer
)
from client.permissions import IsAccountOwnerOrStaff


class StandardPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


class QuestionTagListView(ListAPIView):
    """List all question tags."""
    permission_classes = [AllowAny]
    serializer_class = QuestionTagListSerializer
    queryset = QuestionTag.objects.all().order_by('name')
    pagination_class = None


class QuestionListCreateView(GenericAPIView):
    permission_classes = [AllowAny]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['title', 'body', 'tags__name']
    ordering_fields = ['created_at', 'vote_score', 'answer_count']
    ordering = ['-is_pinned', '-created_at']
    pagination_class = StandardPagination

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return QuestionCreateUpdateSerializer
        return QuestionSerializer

    def get_queryset(self):
        queryset = Question.objects.filter(
            is_deleted=False
        ).select_related('author').prefetch_related('tags')

        # Filters
        is_open = self.request.query_params.get('is_open')
        if is_open is not None:
            queryset = queryset.filter(is_open=is_open.lower() == 'true')

        tag = self.request.query_params.get('tag')
        if tag:
            queryset = queryset.filter(tags__slug=tag)

        author_id = self.request.query_params.get('author')
        if author_id:
            try:
                uuid.UUID(author_id)
                queryset = queryset.filter(author_id=author_id)
            except (ValueError, AttributeError):
                pass

        return queryset

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def create(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return Response(
                {"detail": "Authentication is required to ask a question."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        question = serializer.save(author=request.user)

        # Return detailed serializer
        detail_serializer = QuestionDetailSerializer(question, context={'request': request})
        return Response(detail_serializer.data, status=status.HTTP_201_CREATED)


class QuestionDetailView(GenericAPIView):
    permission_classes = [AllowAny]

    def get_queryset(self):
        return Question.objects.filter(is_deleted=False).select_related('author').prefetch_related('tags')

    def get_serializer_class(self):
        return QuestionDetailSerializer

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, context={'request': request})
        return Response(serializer.data)

    def patch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return Response({"detail": "Authentication required."}, status=status.HTTP_401_UNAUTHORIZED)

        instance = self.get_object()
        if not (request.user.is_staff or instance.author_id == request.user.id):
            return Response({"detail": "You cannot edit this question."}, status=status.HTTP_403_FORBIDDEN)

        serializer = QuestionCreateUpdateSerializer(instance, data=request.data, partial=True, context={'request': request})
        serializer.is_valid(raise_exception=True)
        serializer.save()

        # Return detailed serializer
        detail_serializer = QuestionDetailSerializer(instance, context={'request': request})
        return Response(detail_serializer.data)

    def delete(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return Response({"detail": "Authentication required."}, status=status.HTTP_401_UNAUTHORIZED)

        instance = self.get_object()
        if not (request.user.is_staff or instance.author_id == request.user.id):
            return Response({"detail": "You cannot delete this question."}, status=status.HTTP_403_FORBIDDEN)

        instance.soft_delete()
        return Response({"detail": "Question deleted."}, status=status.HTTP_200_OK)

    def get_object(self):
        return get_object_or_404(self.get_queryset(), pk=self.kwargs['pk'])


class QuestionActionView(GenericAPIView):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Question.objects.filter(is_deleted=False)

    def get_object(self):
        return get_object_or_404(self.get_queryset(), pk=self.kwargs['pk'])

    def post(self, request, *args, **kwargs):
        action = request.data.get('action')
        question = self.get_object()

        if action == 'close':
            if not (request.user.is_staff or question.author_id == request.user.id):
                return Response({"detail": "You cannot close this question."}, status=status.HTTP_403_FORBIDDEN)
            question.close()
            return Response({"detail": "Question closed."})

        elif action == 'reopen':
            if not (request.user.is_staff or question.author_id == request.user.id):
                return Response({"detail": "You cannot reopen this question."}, status=status.HTTP_403_FORBIDDEN)
            question.reopen()
            return Response({"detail": "Question reopened."})

        elif action == 'pin':
            if not request.user.is_staff:
                return Response({"detail": "Only staff can pin questions."}, status=status.HTTP_403_FORBIDDEN)
            question.is_pinned = not question.is_pinned
            question.save(update_fields=['is_pinned', 'updated_at'])
            return Response({"detail": f"Question {'pinned' if question.is_pinned else 'unpinned'}."})

        return Response({"detail": "Invalid action."}, status=status.HTTP_400_BAD_REQUEST)


class QuestionAnswerListCreateView(GenericAPIView):
    permission_classes = [AllowAny]
    pagination_class = StandardPagination

    def get_question(self):
        return get_object_or_404(Question.objects.filter(is_deleted=False), pk=self.kwargs['pk'])

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return AnswerCreateSerializer
        return AnswerSerializer

    def get_queryset(self):
        question = self.get_question()
        return Answer.objects.filter(
            question=question,
            parent__isnull=True,
            is_deleted=False
        ).select_related('author').prefetch_related('replies__author')

    def list(self, request, *args, **kwargs):
        question = self.get_question()
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(page, many=True, context={'request': request})
        return self.get_paginated_response(serializer.data) if page else Response(serializer.data)

    def create(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return Response({"detail": "Authentication is required to answer."}, status=status.HTTP_401_UNAUTHORIZED)

        question = self.get_question()

        if not question.is_open:
            return Response({"detail": "This question is closed for answers."}, status=status.HTTP_400_BAD_REQUEST)

        if question.is_deleted:
            return Response({"detail": "This question has been deleted."}, status=status.HTTP_400_BAD_REQUEST)

        serializer = self.get_serializer(data=request.data, context={'question': question, 'request': request})
        serializer.is_valid(raise_exception=True)
        answer = serializer.save(question=question, author=request.user)

        return Response(AnswerSerializer(answer, context={'request': request}).data, status=status.HTTP_201_CREATED)


class AnswerDetailView(GenericAPIView):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Answer.objects.select_related('author', 'question', 'parent')

    def get_object(self):
        return get_object_or_404(self.get_queryset(), pk=self.kwargs['pk'])

    def get_serializer_class(self):
        if self.request.method in ['PATCH', 'PUT']:
            return AnswerUpdateSerializer
        return AnswerSerializer

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, context={'request': request})
        return Response(serializer.data)

    def patch(self, request, *args, **kwargs):
        instance = self.get_object()
        if not (request.user.is_staff or instance.author_id == request.user.id):
            return Response({"detail": "You cannot edit this answer."}, status=status.HTTP_403_FORBIDDEN)

        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(AnswerSerializer(instance, context={'request': request}).data)

    def delete(self, request, *args, **kwargs):
        instance = self.get_object()
        if not (request.user.is_staff or instance.author_id == request.user.id):
            return Response({"detail": "You cannot delete this answer."}, status=status.HTTP_403_FORBIDDEN)

        instance.soft_delete()
        return Response({"detail": "Answer deleted."}, status=status.HTTP_200_OK)


class AnswerActionView(GenericAPIView):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Answer.objects.select_related('author', 'question')

    def get_object(self):
        return get_object_or_404(self.get_queryset(), pk=self.kwargs['pk'])

    def post(self, request, *args, **kwargs):
        action = request.data.get('action')
        answer = self.get_object()

        if action == 'accept':
            if answer.question.author_id != request.user.id and not request.user.is_staff:
                return Response({"detail": "Only the question author can accept answers."}, status=status.HTTP_403_FORBIDDEN)
            answer.accept()
            return Response({"detail": "Answer accepted."})

        elif action == 'unaccept':
            if answer.question.author_id != request.user.id and not request.user.is_staff:
                return Response({"detail": "Only the question author can unaccept answers."}, status=status.HTTP_403_FORBIDDEN)
            answer.unaccept()
            return Response({"detail": "Answer unaccepted."})

        elif action == 'restore':
            if answer.author_id != request.user.id and not request.user.is_staff:
                return Response({"detail": "You cannot restore this answer."}, status=status.HTTP_403_FORBIDDEN)
            answer.restore()
            return Response({"detail": "Answer restored."})

        return Response({"detail": "Invalid action."}, status=status.HTTP_400_BAD_REQUEST)


class VoteView(GenericAPIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        target_type = kwargs.get('target_type')  # 'question' or 'answer'
        target_id = kwargs.get('pk')

        if target_type == 'question':
            target = get_object_or_404(Question, pk=target_id, is_deleted=False)
            if target.author_id == request.user.id:
                return Response({"detail": "You cannot vote on your own question."}, status=status.HTTP_400_BAD_REQUEST)
            target_field = 'question'
        elif target_type == 'answer':
            target = get_object_or_404(Answer, pk=target_id, is_deleted=False)
            if target.author_id == request.user.id:
                return Response({"detail": "You cannot vote on your own answer."}, status=status.HTTP_400_BAD_REQUEST)
            target_field = 'answer'
        else:
            return Response({"detail": "Invalid target type."}, status=status.HTTP_400_BAD_REQUEST)

        serializer = VoteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        vote, created = Vote.objects.update_or_create(
            voter=request.user,
            **{target_field: target},
            defaults={"value": serializer.validated_data["value"]},
        )

        # Return vote score
        target.refresh_from_db()
        return Response({
            "vote": vote.value,
            "vote_score": target.vote_score,
            "created": created
        })

    def delete(self, request, *args, **kwargs):
        target_type = kwargs.get('target_type')
        target_id = kwargs.get('pk')

        if target_type == 'question':
            target = get_object_or_404(Question, pk=target_id, is_deleted=False)
            target_field = 'question'
        elif target_type == 'answer':
            target = get_object_or_404(Answer, pk=target_id, is_deleted=False)
            target_field = 'answer'
        else:
            return Response({"detail": "Invalid target type."}, status=status.HTTP_400_BAD_REQUEST)

        Vote.objects.filter(voter=request.user, **{target_field: target}).delete()

        target.refresh_from_db()
        return Response({
            "vote": None,
            "vote_score": target.vote_score,
        })


class QuestionShareView(GenericAPIView):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Question.objects.filter(is_deleted=False)

    def get_object(self):
        return get_object_or_404(self.get_queryset(), pk=self.kwargs['pk'])

    def get_serializer_class(self):
        return QuestionShareSerializer

    def post(self, request, *args, **kwargs):
        question = self.get_object()
        serializer = self.get_serializer(data=request.data, context={'question': question, 'request': request})
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response({
            "detail": "Share recorded.",
            "share_count": question.share_count,
        }, status=status.HTTP_201_CREATED)

    def get(self, request, *args, **kwargs):
        question = self.get_object()
        shares = question.shares.select_related('shared_by').all()
        serializer = QuestionShareListSerializer(shares, many=True)
        return Response(serializer.data)


class AnswerReportView(GenericAPIView):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return AnswerReport.objects.select_related('answer', 'reporter', 'resolved_by')

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return AnswerReportCreateSerializer
        if self.request.method in ['PATCH', 'PUT']:
            return AnswerReportResolveSerializer
        return AnswerReportSerializer

    def list(self, request, *args, **kwargs):
        # Only staff can list all reports
        if not request.user.is_staff:
            return Response({"detail": "Permission denied."}, status=status.HTTP_403_FORBIDDEN)

        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(page, many=True)
        return self.get_paginated_response(serializer.data) if page else Response(serializer.data)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(AnswerReportSerializer(serializer.instance).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def resolve(self, request, pk):
        if not request.user.is_staff:
            return Response({"detail": "Permission denied."}, status=status.HTTP_403_FORBIDDEN)

        report = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        if serializer.validated_data['action'] == 'resolve':
            report.is_resolved = True
            report.resolved_by = request.user
            report.resolved_at = timezone.now()
            if serializer.validated_data.get('resolution_note'):
                report.details += f"\n\n[Resolution]: {serializer.validated_data['resolution_note']}"
        else:
            report.is_resolved = False
            report.resolved_by = None
            report.resolved_at = None

        report.save()
        return Response(AnswerReportSerializer(report).data)


class QuestionShareListView(ListAPIView):
    serializer_class = QuestionShareListSerializer

    def get_queryset(self):
        question = get_object_or_404(Question, pk=self.kwargs['pk'])
        return question.shares.select_related('shared_by').all()