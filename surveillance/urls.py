from django.urls import path

from . import views

app_name = 'surveillance'

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("support/", views.support, name="support"),
    path("data/", views.data_table, name="data_table"),
    path("map/", views.map_view, name="map"),
    path("data-quality/", views.data_quality, name="data_quality"),
    path("upload/", views.upload, name="upload"),
    path("country/<str:iso3>/", views.country_detail, name="country_detail"),
    path("export/data.<str:fmt>", views.export_data, name="export_data"),
    path("export/support.<str:fmt>", views.export_support, name="export_support"),
]
