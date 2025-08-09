from django.urls import path
from .views import clear_alert_flag, home, about, contact, payment_success, privacy, careers, profile_view, send_whatsapp_alert, terms, ResponsibleDisclosure, addRestaurant, rideWithUs, test_notification, update_avatar
from .views import userLogin, user_view_menu, UserRegistration_view,user_logout
from .views  import registration_success, user_profile,order_confirmation, order_detail, profile_section, dashboard_home,user_active_orders,order_user_history,support, view_cart, add_to_cart, remove_from_cart, change_quantity,CustomPasswordChangeView,contact_form
from django.contrib.auth.views import LogoutView

from user_app import views

urlpatterns = [
    path('',home, name='home' ),
    path('category/<slug:category_slug>/', views.category_items, name='category_items'),
    path('user-registration/',UserRegistration_view, name='user_registration' ),
    path('registration-success/',registration_success, name='registration_success' ),
    path('about/',about, name='about' ),
    path('contact-us/',contact, name='contact' ),
    path('privacy/',privacy, name='privacy' ),
    path('careers/',careers, name='careers' ),
    path('terms-and-conditions/',terms, name='terms-and-conditions' ),
    path('Responsible-disclosure/',ResponsibleDisclosure, name='responsible-disclosure' ),
    path('add-restaurant/',addRestaurant, name='add-restaurant' ),
    path('ride-with-us/',rideWithUs, name='ride-with-us' ),
    path('restaurant/<int:restaurant_id>/menu/', user_view_menu, name='user_view_menu'),
    
    path('user-login/',userLogin, name='user_login' ),
    path('user/home/', dashboard_home, name='user-dashboard'),
    path('orders/<int:order_id>/', order_detail, name='order_detail'),
    path('user/profile', profile_section, name='profile-section'),
    path('user/home/', dashboard_home, name='dashboard_home'),
    path('user/active/', user_active_orders, name='user_active_orders'),
    path('user/history/', order_user_history, name='order_user_history'),
    path('order/<int:order_id>/feedback/', views.write_order_feedback, name='write_feedback'),

    path('user/support/', views.user_support, name='user_support_portal'),

    path('user/cart/', view_cart, name='view_cart'),
    path('user/cart/add/<int:item_id>/', add_to_cart, name='add_to_cart'),
    path('user/cart/remove/<int:item_id>/', remove_from_cart, name='remove_from_cart'),
    path('user/cart/<int:item_id>/<str:action>/', change_quantity, name='change_quantity'),
    path('order-now/<int:item_id>/', views.order_now, name='order_now'),

    path('logout/', user_logout, name='user_logout'),
    path('checkout/', views.checkout, name='checkout'),
    path('order-confirmation/<int:order_id>/', order_confirmation, name='order_confirmation'),
    path('payment/success/', payment_success, name='payment_success'),

    path('restaurant/<int:restaurant_id>/review/', views.submit_review, name='submit_review'),
    path('profile/', views.profile_view, name='profile'),
    path('profile/update/', profile_view, name='update_profile'),

    path('profile/update-avatar/', update_avatar, name='update_avatar'),
    path('change-password/', CustomPasswordChangeView.as_view(), name='change_password'),
    path('api/send-whatsapp/', send_whatsapp_alert, name='send_whatsapp'),
    path('test-notification/', test_notification, name='test_notification'),
    path('contact-form/', views.contact_form, name='contact-form'),
    path('clear-alert-flag/', clear_alert_flag, name='clear_alert_flag'),



]