from rest_framework.routers import DefaultRouter
from django.urls import path, include
from . import views

router = DefaultRouter()
router.register('posts', views.PostViewSet, basename='posts')
router.register('comments', views.CommentViewSet, basename='comments')
router.register('reports', views.ReportViewSet, basename='reports')
router.register(r'saved-posts', views.SavedPostViewSet, basename='saved-posts')

urlpatterns = router.urls