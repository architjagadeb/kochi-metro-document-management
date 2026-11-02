from django.urls import path

from . import views

urlpatterns = [
    path('', views.analytics_dashboard, name='analytics_dashboard'),
    path('', views.analytics_dashboard, name='analytics'),
    path('csv/', views.export_csv_view, name='analytics_csv'),
    path('export/', views.export_csv_view, name='analytics_export_csv'),
]
