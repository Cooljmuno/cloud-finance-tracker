from uuid import UUID

from django.db.models.deletion import RestrictedError
from django.utils.dateparse import parse_date
from rest_framework import status, viewsets
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.permissions import IsAuthenticated

from .models import Category, FinancialAccount, Transaction
from .permissions import IsFinanceResourceOwner
from .serializers import CategorySerializer, FinancialAccountSerializer, TransactionSerializer


class Conflict(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "The resource conflicts with existing data."
    default_code = "conflict"


class OwnerViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsFinanceResourceOwner]

    def get_queryset(self):
        if not self.request.user.is_authenticated:
            return super().get_queryset().none()
        return super().get_queryset().filter(owner=self.request.user)

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)


class FinancialAccountViewSet(OwnerViewSet):
    queryset = FinancialAccount.objects.all()
    serializer_class = FinancialAccountSerializer

    def perform_destroy(self, instance):
        if instance.transactions.exists():
            raise Conflict(
                "Accounts with transactions cannot be deleted; mark the account inactive."
            )
        try:
            instance.delete()
        except RestrictedError as error:
            raise Conflict(
                "Accounts with transactions cannot be deleted; mark the account inactive."
            ) from error


class CategoryViewSet(OwnerViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer

    def perform_destroy(self, instance):
        if instance.transactions.exists():
            raise Conflict(
                "Categories with transactions cannot be deleted; mark the category inactive."
            )
        try:
            instance.delete()
        except RestrictedError as error:
            raise Conflict(
                "Categories with transactions cannot be deleted; mark the category inactive."
            ) from error


class TransactionViewSet(OwnerViewSet):
    queryset = Transaction.objects.select_related("account", "category")
    serializer_class = TransactionSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        params = self.request.query_params

        if account_id := params.get("account"):
            queryset = queryset.filter(account_id=self._parse_uuid("account", account_id))
        if category_id := params.get("category"):
            queryset = queryset.filter(category_id=self._parse_uuid("category", category_id))
        if transaction_status := params.get("status"):
            valid_statuses = {choice for choice, _ in Transaction.Status.choices}
            if transaction_status not in valid_statuses:
                raise ValidationError({"status": "Use pending or posted."})
            queryset = queryset.filter(status=transaction_status)

        date_from = self._parse_date("date_from", params.get("date_from"))
        date_to = self._parse_date("date_to", params.get("date_to"))
        if date_from and date_to and date_from > date_to:
            raise ValidationError({"date_to": "Must be on or after date_from."})
        if date_from:
            queryset = queryset.filter(transaction_date__gte=date_from)
        if date_to:
            queryset = queryset.filter(transaction_date__lte=date_to)

        return queryset

    @staticmethod
    def _parse_uuid(name, value):
        try:
            return UUID(value)
        except (TypeError, ValueError, AttributeError) as error:
            raise ValidationError({name: "Must be a valid UUID."}) from error

    @staticmethod
    def _parse_date(name, value):
        if not value:
            return None
        try:
            parsed = parse_date(value)
        except ValueError as error:
            raise ValidationError({name: "Use a valid date in YYYY-MM-DD format."}) from error
        if parsed is None:
            raise ValidationError({name: "Use YYYY-MM-DD."})
        return parsed
