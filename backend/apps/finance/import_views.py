from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .imports import commit_import, preview_import
from .models import FinancialAccount, ImportBatch
from .permissions import IsFinanceResourceOwner
from .serializers import ImportBatchSerializer


class ImportUploadSerializer(serializers.Serializer):
    account = serializers.UUIDField()
    file = serializers.FileField(allow_empty_file=True)
    preview_token = serializers.CharField(required=False, trim_whitespace=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.context.get("require_preview_token"):
            self.fields["preview_token"].required = True

    def validate_account(self, value):
        account = FinancialAccount.objects.filter(
            pk=value,
            owner=self.context["request"].user,
        ).first()
        if account is None:
            raise NotFound()
        return account


class ImportBatchViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ImportBatchSerializer
    permission_classes = [IsAuthenticated, IsFinanceResourceOwner]

    def get_queryset(self):
        if not self.request.user.is_authenticated:
            return ImportBatch.objects.none()
        return ImportBatch.objects.select_related("account").filter(owner=self.request.user)

    def upload_serializer(self, request, *, require_preview_token=False):
        serializer = ImportUploadSerializer(
            data=request.data,
            context={"request": request, "require_preview_token": require_preview_token},
        )
        serializer.is_valid(raise_exception=True)
        return serializer

    @action(detail=False, methods=["post"], parser_classes=[MultiPartParser, FormParser])
    def preview(self, request):
        serializer = self.upload_serializer(request)
        return Response(
            preview_import(
                request.user,
                serializer.validated_data["account"],
                serializer.validated_data["file"],
            )
        )

    @action(detail=False, methods=["post"], parser_classes=[MultiPartParser, FormParser])
    def commit(self, request):
        serializer = self.upload_serializer(request, require_preview_token=True)
        batch, duplicate = commit_import(
            request.user,
            serializer.validated_data["account"],
            serializer.validated_data["file"],
            serializer.validated_data["preview_token"],
        )
        return Response(
            {"batch": ImportBatchSerializer(batch).data, "duplicate": duplicate},
            status=status.HTTP_200_OK if duplicate else status.HTTP_201_CREATED,
        )
