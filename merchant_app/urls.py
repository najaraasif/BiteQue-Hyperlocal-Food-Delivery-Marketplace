from django.urls import path
from merchant_app import views
from django.contrib.auth.views import LogoutView

urlpatterns = [
    path('merchant-register/', views.merchant_register_view, name='merchant_register'),
    path('merchant-register/success/', views.merchant_register_success, name='merchant_register_success'),
    path('merchant-login/', views.merchant_login, name='merchant_login'),
    path('logout/', LogoutView.as_view(next_page='merchant_login'), name='merchant_logout'),
    path('restaurant-status/', views.post_login_redirect, name='post-login-redirect'),
    path('add-restaurant', views.add_restaurant_view, name='add_restaurant'),
    path('merchant-dashboard/restaurant-success/', views.restaurant_success, name='restaurant_success'),

    path('awaiting-approval/', views.awaiting_approval_view, name='awaiting-approval'),
    path('merchant-dashboard/', views.merchant_dashboard, name='merchant_dashboard'),
    path('awaiting-approval/', views.merchant_dashboard, name='awaiting-approval'),
    path('merchant/orders/', views.merchant_orders, name='merchant_orders'),
    path('merchant/orders/confirm/<int:order_id>/', views.confirm_order, name='confirm_order'),
    path('merchant/orders/ready/<int:order_id>/', views.mark_order_ready, name='mark_order_ready'),


    path('merchant-dashboard/menu/', views.menu_dashboard_view, name='menu_dashboard'),
    path('menu/add/', views.add_item, name='add_item'),
    path('menu/edit/<int:item_id>/', views.edit_item, name='edit_menu_item'),
    path('merchant-logout/', LogoutView.as_view(next_page='merchant_login'), name='merchant_logout'),

    path('merchant/bank-accounts/', views.bank_account_list, name='bank_account_list'),
    path('merchant/bank-accounts/add/', views.add_bank_account, name='add_bank_account'),
    path('merchant/bank-accounts/edit/<int:account_id>/', views.edit_bank_account, name='edit_bank_account'),
    path('merchant/bank-accounts/delete/<int:account_id>/', views.delete_bank_account, name='delete_bank_account'),

]