from django.urls import path
from .views import sensor_data
from .import views

urlpatterns = [
    path("api/sensor-data/", sensor_data, name="sensor_data"),
    path("dashboard/", views.dashboard, name="dashboard"),
]
