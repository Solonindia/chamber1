from django.urls import path, re_path
from .import views
from .import views_admin
from django.contrib.auth import views as auth_views

urlpatterns = [
    path("", views_admin.redirect_to_default_chamber, name="home"),
    re_path(r'^(?P<ch>ch[123])/$', views.minute_table, name='sensor_data_page'),
    re_path(r'^chart/(?P<ch>ch[123])/$', views.chart_page, name='chart_page'),
    re_path(r'^emb/api/(?P<ch>ch[123])/sensor-data/$', views.ingest_sensor_data, name='ingest_sensor_data'),
    re_path(r'^api/range/(?P<ch>ch[123])/$', views.range_rows, name='range_rows'),
    re_path(r'^api/chart_data/(?P<ch>ch[123])/$', views.chart_data, name='chart_data'),
    re_path(r'^api/download_csv/(?P<ch>ch[123])/?$', views.download_csv, name='download_csv'),
    re_path(r'^api/download_pdf/(?P<ch>ch[123])/?$', views.download_pdf, name='download_pdf'),

    path("login/", auth_views.LoginView.as_view(template_name="login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("post-login/", views_admin.post_login_redirect, name="post_login"),  # role-based jump
    path("users/", views_admin.user_list, name="user_list"),
    path("users/create/", views_admin.user_create, name="user_create"),
    path("users/<int:user_id>/edit/", views_admin.user_edit, name="user_edit"),
    path("users/<int:user_id>/delete/", views_admin.user_delete, name="user_delete"),
    
]

