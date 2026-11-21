from django.urls import path
from . import views

app_name = "gallery_signups"
urlpatterns = [
    path("", views.calendar, name="calendar"),
    path("member-login/", views.member_login, name="member_login"),
    path("member-logout/", views.member_logout, name="member_logout"),
    path("claim/<int:slot_id>/", views.claim_slot, name="claim_slot"),
    path("change/<int:slot_id>/", views.change_slot, name="change_slot"),
    path("month/<int:event_id>/", views.month_detail, name="month"),
    path("artists/", views.artist_information, name="artist_information"),
    path("artists/calendar/", views.public_artist_calendar, name="public_artist_calendar"),
    path("artists/apply/", views.artist_application, name="artist_application"),
    path("manage/login/", views.admin_login, name="admin_login"),
    path("manage/logout/", views.admin_logout, name="admin_logout"),
    path("manage/", views.manage, name="manage"),
    path("manage/slot/<int:slot_id>/", views.save_slot, name="save_slot"),
    path("manage/event/<int:event_id>/", views.save_event, name="save_event"),
    path("manage/member-password/", views.owner_settings, name="owner_settings"),
    path("manage/administrators/", views.owner_administrators, name="owner_administrators"),
    path("manage/history/", views.signup_history, name="signup_history"),
    path("manage/applications/", views.application_list, name="application_list"),
    path("manage/applications/<int:application_id>/", views.application_detail, name="application_detail"),
    path("manage/applications/<int:application_id>/approve/", views.approve_application, name="approve_application"),
    path("manage/applications/<int:application_id>/decline/", views.decline_application, name="decline_application"),
]
