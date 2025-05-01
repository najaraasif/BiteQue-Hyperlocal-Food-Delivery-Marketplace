from django.urls import path
from merchant_app import views
urlpatterns = [
    path('merchant-register/', views.merchantRegistration, name='merchant_register'),
    path('merchant-register/success/', views.merchant_register_success, name='merchant_register_success'),
    path('merchant-login/', views.merchant_login, name='merchant_login'),
    path('add-restaurant/', views.addRestaurant, name='add-restaurant'),
    path('merchant-dashboard/', views.dashboard_home, name='dashboard_home'),
    path('merchant-dashboard/inventory', views.inventory_management, name='inventory_management'),
    path('merchant-dashboard/orders', views.order_list, name='merchant_orders'),
    path('merchant-dashboard/payments', views.payment_list, name='merchant_payments'),





]