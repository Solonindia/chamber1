from django.urls import path
from .import views


urlpatterns = [
    path('', views.minute_table, name='sensor_data_page'),
    path("api/download_csv/", views.download_csv, name="download_csv"),
    path('api/range/',  views.range_rows,  name='range_rows'),  # uses window + every
    path("chart/", views.chart_page, name="chart_page"),
    path("api/chart_data/", views.chart_data, name="chart_data"),
]
