from django.urls import path

from . import views

urlpatterns = [
    path('', views.document_list, name='document_list'),
    path('upload/', views.upload_document, name='document_upload'),
    path('archive/', views.archived_document_list, name='document_archive_list'),
    path('<int:id>/', views.document_detail, name='document_detail'),
    path('<int:id>/archive/', views.toggle_document_archive, name='document_toggle_archive'),
    path('<int:id>/new-version/', views.upload_new_version, name='document_upload_new_version'),
    path('<int:id>/resubmit/', views.resubmit_document, name='document_resubmit'),
    path('<int:id>/download/<int:version_id>/', views.document_version_download, name='document_version_download'),
]
