from django.urls import path
from rider_app import views
from rider_app.views import RiderLoginView, rider_dashboard

urlpatterns = [
    path('dashboard/', rider_dashboard, name='rider_dashboard'),
    path('registration/', views.rider_registration, name='rider_registration'),
    path('registration-success/', views.registration_success, name='registration_success'),
    path('rider-login/', RiderLoginView.as_view(), name='rider-login'),
    path('update-availability/', views.update_availability, name='update_availability'),
    path('orders/accept/<int:order_id>/', views.accept_order, name='accept_order'),
    path('orders/reject/<int:order_id>/', views.reject_order, name='reject_order'),
]

  
