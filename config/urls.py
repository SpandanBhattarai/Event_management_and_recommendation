"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path
from events.views import home
from events.views import register_view, login_view, logout_view
from events import views

urlpatterns = [
    path('admin/', admin.site.urls),
     path('', home, name='home'),
     path('register/', register_view, name='register'),
     path('login/', login_view, name='login'),
     path('logout/', logout_view, name='logout'),
     path ('events/', views.events_view, name='events'),
     path ('venues/', views.venues_view, name='venues'),
     path('contact/', views.contact_view, name='contact'),
     path('save_location/', views.save_location, name='save_location'),
     path('buy-ticket/<int:event_id>/', views.buy_ticket, name='buy_ticket'),
     path('khalti/return/', views.khalti_return, name='khalti_return'),
     path('tickets/', views.tickets_view, name='tickets'),
     path('profile/preferences/', views.profile_preferences_view, name='profile_preferences'),
]

