from django.urls import path
from . import views

urlpatterns = [
    path("", views.PatientListView.as_view()),
    path("<str:patient_id>/documents/", views.PatientDocumentUploadView.as_view()),
    path("<str:patient_id>/analyze/", views.AnalyzeView.as_view()),
    path("<str:patient_id>/approve/", views.ApproveView.as_view()),
    path("<str:patient_id>/timeline/", views.TimelineView.as_view()),
    path("<str:patient_id>/chat/", views.ChatView.as_view()),
]
