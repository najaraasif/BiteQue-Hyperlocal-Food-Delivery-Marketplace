from django.urls import path
from rider_app import views
from rider_app.views import RiderLoginView, rider_dashboard, rider_earnings, rider_logout

app_name = 'rider'

urlpatterns = [
    path('dashboard/', views.rider_dashboard, name='dashboard'),
    path('registration/', views.rider_registration, name='registration'),
    path('registration-success/', views.registration_success, name='registration_success'),
    path('rider-login/', RiderLoginView.as_view(), name='rider-login'),
    path('update-availability/', views.update_availability, name='update_availability'),
    path('orders/accept/<int:order_id>/', views.accept_order, name='accept_order'),
    path('bank-details/', views.bank_details, name='bank_details'),
    path('logout/', views.rider_logout, name='logout'),
    path('earnings/', views.rider_earnings, name='earnings'),
    path('orders/deliver/<int:order_id>/', views.mark_delivered, name='mark_delivered'),
]

  
