from django.urls import path
from rider_app import views
from rider_app.views import RiderLoginView, rider_dashboard

urlpatterns = [
    path('dashboard/', rider_dashboard, name='rider_dashboard'),
    path('registration/', views.rider_registration, name='rider_registration'),
    path('registration-success/', views.registration_success, name='registration_success'),
    path('rider-login/', RiderLoginView.as_view(), name='rider-login'),
]   
