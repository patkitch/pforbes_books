from django.urls import path
from . import views

app_name = "gallery_signups"
urlpatterns = [
    path("", views.calendar, name="calendar"),
    path("member-login/", views.member_login, name="member_login"),
    path("member-logout/", views.member_logout, name="member_logout"),
    path("claim/<int:slot_id>/", views.claim_slot, name="claim_slot"),
    path("manage/login/", views.admin_login, name="admin_login"),
    path("manage/logout/", views.admin_logout, name="admin_logout"),
    path("manage/", views.manage, name="manage"),
    path("manage/slot/<int:slot_id>/", views.save_slot, name="save_slot"),
    path("manage/event/<int:event_id>/", views.save_event, name="save_event"),
    path("manage/member-password/", views.owner_settings, name="owner_settings"),
    path("manage/administrators/", views.owner_administrators, name="owner_administrators"),
]
