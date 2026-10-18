from rest_framework.routers import DefaultRouter

from .import_views import ImportBatchViewSet
from .views import CategoryViewSet, FinancialAccountViewSet, TransactionViewSet

router = DefaultRouter()
router.register("accounts", FinancialAccountViewSet, basename="account")
router.register("categories", CategoryViewSet, basename="category")
router.register("transactions", TransactionViewSet, basename="transaction")
router.register("imports", ImportBatchViewSet, basename="import-batch")

urlpatterns = router.urls
