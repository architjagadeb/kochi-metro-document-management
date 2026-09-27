from django.urls import path

from . import views

urlpatterns = [
    path('mark-all-read/', views.mark_all_notifications_read, name='notifications_mark_all_read'),
    path('<int:id>/mark-read/', views.mark_notification_read, name='notifications_mark_read'),
]
