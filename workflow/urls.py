from django.urls import path
from . import views

urlpatterns = [
    path('pending/', views.pending_list, name='workflow_pending_list'),
    path('<int:document_id>/approve/', views.approve_document, name='workflow_approve_document'),
    path('<int:document_id>/reject/', views.reject_document, name='workflow_reject_document'),
]
