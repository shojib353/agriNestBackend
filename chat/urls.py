from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register('connections', views.ChatConnectionViewSet, basename='chat-connections')
router.register('messages', views.MessageViewSet, basename='chat-messages')
router.register(r'users', views.ShowAllUserViewSet, basename='users')


urlpatterns = router.urls