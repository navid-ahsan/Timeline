from django.urls import path
from . import views

urlpatterns = [
    path("", views.LawSearchView.as_view()),
]
