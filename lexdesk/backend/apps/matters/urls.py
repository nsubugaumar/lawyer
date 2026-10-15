from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("matters", views.MatterViewSet, basename="matter")
router.register("parties", views.PartyViewSet, basename="party")
router.register("tasks", views.TaskViewSet, basename="task")
router.register("notes", views.NoteViewSet, basename="note")
router.register("diary", views.CourtDiaryViewSet, basename="diary")

urlpatterns = router.urls
