from django.urls import path
from rest_framework.routers import DefaultRouter

from .import_views import ImportBatchViewSet
from .planning_views import MonthlyBudgetViewSet, MonthlyReportView, RuleViewSet
from .views import CategoryViewSet, FinancialAccountViewSet, TransactionViewSet

router = DefaultRouter()
router.register("accounts", FinancialAccountViewSet, basename="account")
router.register("categories", CategoryViewSet, basename="category")
router.register("transactions", TransactionViewSet, basename="transaction")
router.register("imports", ImportBatchViewSet, basename="import-batch")
router.register("rules", RuleViewSet, basename="rule")
router.register("budgets", MonthlyBudgetViewSet, basename="budget")

urlpatterns = [
    path("reports/monthly/", MonthlyReportView.as_view(), name="monthly-report"),
    *router.urls,
]
