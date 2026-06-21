from django.urls import path

from . import views

app_name = 'surveillance'

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("support/", views.support, name="support"),
    path("data/", views.data_table, name="data_table"),
]
