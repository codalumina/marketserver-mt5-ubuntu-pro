from django.urls import path

from . import views

urlpatterns = [
    path("stat/", views.server_stat, name="server_stat"),
    path("recent/", views.recent_price_action, name="recent_price_action"),
    path("symbols/all/", views.all_symbols, name="all_symbols"),
    path("calendar/", views.economic_calendar, name="economic_calendar"),
]
