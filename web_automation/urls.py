from django.urls import path
from . import views, vincent_views
from . import vincent_create_views

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
    # Vincent — Original Artwork (read-only preview; no product creation)
    path(
        "vincent/original-artwork/",
        vincent_views.vincent_intake,
        name="vincent_intake",
    ),
        path(
        "vincent/original-artwork/preview/",
        vincent_views.vincent_preview,
        name="vincent_preview",
    ),
    path(
        "vincent/original-artwork/draft-review/",
        vincent_views.vincent_draft_review,
        name="vincent_draft_review",
    ),
        path(
        "vincent/original-artwork/confirm/",
        vincent_views.vincent_confirm_draft,
        name="vincent_confirm_draft",
    ),
        path(
        "vincent/original-artwork/create-draft/",
        vincent_create_views.vincent_create_draft,
        name="vincent_create_draft",
    ),
]

