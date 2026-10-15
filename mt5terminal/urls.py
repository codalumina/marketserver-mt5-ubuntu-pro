from django.urls import path

from . import views

urlpatterns = [
    # Server status
    path("stat/", views.server_stat, name="server_stat"),
    # Market and price action
    path("recent/", views.recent_price_action, name="recent_price_action"),
    path("symbols/all/", views.all_symbols, name="all_symbols"),
    # Calendar
    path("calendar/", views.economic_calendar, name="economic_calendar"),
    # Execution routes
    path("trade/positions/", views.open_positions, name="open_positions"),
    path("trade/execute/", views.execute_trade, name="execute_trade"),
    path("trade/flatten/", views.flatten_positions, name="flatten_positions"),
]
