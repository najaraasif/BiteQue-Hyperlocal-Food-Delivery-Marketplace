from django.urls import path
from .views import home, about, contact, privacy, careers, terms, ResponsibleDisclosure, addRestaurant, rideWithUs, userLogin, user_view_menu

urlpatterns = [
    path('',home, name='home' ),
    path('about/',about, name='about' ),
    path('contact-us/',contact, name='contact' ),
    path('privacy/',privacy, name='privacy' ),
    path('careers/',careers, name='careers' ),
    path('terms-and-conditions/',terms, name='terms-and-conditions' ),
    path('Responsible-disclosure/',ResponsibleDisclosure, name='responsible-disclosure' ),
    path('add-restaurant/',addRestaurant, name='add-restaurant' ),
    path('ride-with-us/',rideWithUs, name='ride-with-us' ),
    
    path('user-login/',userLogin, name='user_login' ),
    path('restaurant/<int:restaurant_id>/menu/', user_view_menu, name='user_view_menu'),


]