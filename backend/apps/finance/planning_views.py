from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import CategorizationRule, MonthlyBudget
from .planning import apply_rules
from .planning_serializers import MonthlyBudgetSerializer, RuleSerializer
from .reports import monthly_report, normalize_currency, parse_month
from .views import OwnerViewSet


class RuleViewSet(OwnerViewSet):
    queryset = CategorizationRule.objects.select_related("category")
    serializer_class = RuleSerializer

    @action(detail=False, methods=["post"])
    def apply(self, request):
        return Response(apply_rules(request.user))


class MonthlyBudgetViewSet(OwnerViewSet):
    queryset = MonthlyBudget.objects.select_related("category")
    serializer_class = MonthlyBudgetSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        if "month" in self.request.query_params:
            queryset = queryset.filter(month=parse_month(self.request.query_params["month"]))
        if "currency" in self.request.query_params:
            queryset = queryset.filter(
                currency=normalize_currency(self.request.query_params["currency"])
            )
        return queryset


class MonthlyReportView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        month = parse_month(request.query_params.get("month"), require_trend=True)
        currency = normalize_currency(request.query_params.get("currency", "USD"))
        return Response(monthly_report(request.user, month, currency))
