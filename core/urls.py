from django.urls import path
from . import views

urlpatterns = [
    path('', views.home_view, name='home'),
    path('query/', views.query_view, name='query'),
    path('api/compounds/', views.compounds_api, name='compounds_api'),
    path('api/metadata/', views.metadata_api, name='metadata_api'),
]