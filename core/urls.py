from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    path('', views.homepage, name='core_home'),  # The route for core/index.html
    path('homelab/', views.homelab, name='homelab'),
    path('weather/', views.weather, name='weather'),
    path('contact/', views.contact, name='contact'),
    path('api/metrics/', views.get_cluster_metrics, name='cluster_metrics'),
    path('api/weather/', views.get_weather_data, name='weather_data'),
    path('api/weather/history/', views.get_weather_history, name='weather_history'),
    path('maintenance/', views.maintenance, name='maintenance'),
]
