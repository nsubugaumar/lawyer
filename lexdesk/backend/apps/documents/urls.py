from rest_framework.routers import DefaultRouter

from .views import DocumentTemplateViewSet, DocumentViewSet, SignatureRequestViewSet

router = DefaultRouter()
router.register("templates", DocumentTemplateViewSet, basename="document-template")
router.register("signatures", SignatureRequestViewSet, basename="signature")
router.register("", DocumentViewSet, basename="document")

urlpatterns = router.urls
