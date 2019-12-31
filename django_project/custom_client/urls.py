from . import views
from django.urls import path

urlpatterns = [
    path('job_details<str:id>', views.job_details, name='job_details'),
    path('company_details<str:id>', views.company_details, name='company_details'),
    path('', views.search, name='index'),
]
