from rest_framework.routers import DefaultRouter

from .views import AuthorityViewSet

router = DefaultRouter()
router.register("", AuthorityViewSet, basename="authority")

urlpatterns = router.urls
