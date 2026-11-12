from django.urls import path
from . import views
app_name="art_inventory"
urlpatterns=[path("",views.home,name="home"),path("artwork/add/",views.artwork_add,name="artwork_add"),path("artwork/<int:pk>/",views.detail,name="detail"),path("print/add/",views.print_add,name="print_add"),path("activity/add/",views.activity_add,name="activity_add")]
