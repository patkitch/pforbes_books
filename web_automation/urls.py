from django.urls import path
from . import views

app_name = "web_automation"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("new-product/", views.new_product_step1, name="new_product_step1"),
    path(
        "new-product/suggestions/",
        views.new_product_suggestions,
        name="new_product_suggestions",
    ),  
    path(
        "new-product/select/",
        views.new_product_select,
        name="new_product_select",
    ), 
    path(
        "new-product/create-draft/",
        views.new_product_create_draft,
        name="new_product_create_draft",
    ),
    path(
        "seo/product/",
        views.seo_product_lookup,
        name="seo_product_lookup",
    ),
    path(
    "seo/product/<int:product_id>/",
    views.seo_product_suggestions,
    name="seo_product_suggestions",
    ),
    path(
        "mira/product/",
        views.mira_product_lookup,
        name="mira_product_lookup",
    ),
    path(
        "mira/product/<int:product_id>/",
        views.mira_blog_suggestions,
        name="mira_blog_suggestions",
    ),

]
