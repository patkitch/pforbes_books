from django.urls import path
from . import views
app_name="art_inventory"
urlpatterns=[
    path("",views.home,name="home"),
    path("artwork/add/",views.artwork_add,name="artwork_add"),
    path("artwork/<int:pk>/",views.detail,name="detail"),
    path("artwork/<int:pk>/edit/",views.artwork_edit,name="artwork_edit"),
    path("artwork/<int:pk>/delete/",views.artwork_delete,name="artwork_delete"),
    path("print/add/",views.print_add,name="print_add"),
    path("print/<int:pk>/delete/",views.print_delete,name="print_delete"),
    path("activity/add/",views.activity_add,name="activity_add"),
    path("reports/",views.inventory_report,name="report"),
]
