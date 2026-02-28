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
     path('events/<int:event_id>/', views.event_detail, name='event_detail'),
     path ('venues/', views.venues_view, name='venues'),
     path('contact/', views.contact_view, name='contact'),
     path('save_location/', views.save_location, name='save_location'),
     path('buy-ticket/<int:event_id>/', views.buy_ticket, name='buy_ticket'),
     path('khalti/return/', views.khalti_return, name='khalti_return'),
     path('tickets/', views.tickets_view, name='tickets'),
     path('profile/preferences/', views.profile_preferences_view, name='profile_preferences'),
     path('dashboard/admin/', views.admin_dashboard, name='admin_dashboard'),
     path('dashboard/admin/events/<int:event_id>/approval/', views.admin_event_approval_action, name='admin_event_approval_action'),
     path('dashboard/admin/users/<int:user_id>/role/', views.admin_user_role_action, name='admin_user_role_action'),
     path('dashboard/admin/users/<int:user_id>/activation/', views.admin_user_activation_action, name='admin_user_activation_action'),
     path('dashboard/organizer/', views.organizer_dashboard, name='organizer_dashboard'),
     path('dashboard/organizer/events/create/', views.organizer_event_create, name='organizer_event_create'),
     path('dashboard/organizer/events/<int:event_id>/edit/', views.organizer_event_edit, name='organizer_event_edit'),
     path('dashboard/organizer/events/<int:event_id>/delete/', views.organizer_event_delete, name='organizer_event_delete'),
     path('dashboard/organizer/events/<int:event_id>/attendees.csv', views.organizer_event_attendees_csv, name='organizer_event_attendees_csv'),
]

