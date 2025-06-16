from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views
from rest_framework_simplejwt.views import TokenObtainPairView,TokenRefreshView

router = DefaultRouter()
router.register(r'rooms', views.RoomViewSet)
router.register(r'complaints', views.ComplaintViewSet)
router.register(r'report',views.ReportViewSet)
router.register(r'departments', views.DepartmentViewSet)
router.register(r'issue-category', views.IssueCatViewset)
router.register(r'TATView', views.TATViewSet)

urlpatterns = [
    path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('admin/', admin.site.urls),
    path('', include(router.urls)),
    path('api/', include(router.urls)),
]