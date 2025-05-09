from django.urls import path
from rider_app import views
from rider_app.views import RiderLoginView, RiderPasswordResetView,RiderPasswordResetDoneView,RiderPasswordResetConfirmView,RiderPasswordResetCompleteView, rider_dashboard, rider_earnings, rider_logout
from django.urls import path, reverse_lazy

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
    path('bank-details/', views.bank_details_list, name='bank_details_list'), 
    path('bank-details/delete/<int:account_id>/', views.delete_bank_account, name='delete_bank_account'),
    path('bank-details/set-primary/<int:account_id>/', views.set_primary_bank_account, name='set_primary_bank_account'),
    path("rider/order/<int:order_id>/", views.rider_order_detail, name="rider_order_detail"),
    path("rider/order/<int:order_id>/accept/", views.accept_order_assignment, name="accept_order_assignment_action"),
    path('password-reset/',
         RiderPasswordResetView.as_view(),
         name='password_reset'),
    path('password-reset/done/',
         RiderPasswordResetDoneView.as_view(),
         name='password_reset_done'),
    path('password-reset-confirm/<uidb64>/<token>/',
         RiderPasswordResetConfirmView.as_view(),
         name='password_reset_confirm'),
    path('password-reset-complete/',
         RiderPasswordResetCompleteView.as_view(),
         name='password_reset_complete'),
]

  
