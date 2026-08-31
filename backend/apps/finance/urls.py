from rest_framework.routers import DefaultRouter

from .views import CategoryViewSet, FinancialAccountViewSet, TransactionViewSet

router = DefaultRouter()
router.register("accounts", FinancialAccountViewSet, basename="account")
router.register("categories", CategoryViewSet, basename="category")
router.register("transactions", TransactionViewSet, basename="transaction")

urlpatterns = router.urls
