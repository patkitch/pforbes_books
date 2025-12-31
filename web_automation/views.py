from django.shortcuts import render, redirect
from .forms import NewProductForm, ProductChoiceForm, SEOProductLookupForm
from .suggestions import generate_product_suggestions 
from django.contrib import messages
from django.utils import timezone

from automation_logs.models import AgentRun, AgentEvent
from agents.pauly.core import create_standard_print_product_from_web
from agents.sam_seo.core import fetch_and_suggest_seo
from django.urls import reverse
from agents.mira.core import fetch_and_generate_blog


def dashboard(request):
    """
    Website Automation Dashboard (skeleton v1).
    Eventually this will show:
      - Catalog tools (Pauly)
      - SEO tools (SamSEO)
      - Design/content tools (Mira)
    For now, just a simple landing page with a link to New Product.
    """
    return render(request, "web_automation/dashboard.html", {})


def new_product_step1(request):
    """
    Step 1: New Product Intake
    - Collect basic info about a new artwork/product for pforbesart.com
    - For now, just echo the submitted data back for review.
    - Later, this will feed Pauly (catalog), SamSEO, and Mira.
    """
    if request.method == "POST":
        form = NewProductForm(request.POST)
        if form.is_valid():
            cleaned = form.cleaned_data
            request.session["new_product_intake"] = cleaned  # store in session for next step
            request.session.modified = True
            context = {
                "form": form,
                
                
            }
            return redirect( "web_automation:new_product_suggestions")
    else:
        form = NewProductForm()

    context = {
        "form": form,
       
    }
    return render(request, "web_automation/new_product_step1.html", context)

def new_product_suggestions(request):
    """
    Step 2: Suggestion Engine
    - Reads intake data from the session (from Step 1)
    - Uses the suggestion engine to generate title/description/alt-text options
    - Renders them in a review page (selection + Step 3 will come later)
    """
    intake = request.session.get("new_product_intake")
    if not intake:
        # If there's no intake data, send user back to step 1
        return redirect("web_automation:new_product_step1")

    suggestions = generate_product_suggestions(intake)
    request.session["new_product_suggestions"] = suggestions
    request.session.modified = True

    context = {
        "intake": intake,
        "suggestions": suggestions,
    }
    return render(request, "web_automation/new_product_suggestions.html", context)
def new_product_select(request):
    """
    Step 3: Selection + Preview
    - Reads intake data and suggestions from the session
    - Lets the user choose final title/short/long/alt
    - Shows a preview of the final copy
    - Stores final copy in the session for the next step (Woo draft creation)
    """
    intake = request.session.get("new_product_intake")
    suggestions = request.session.get("new_product_suggestions")

    if not intake or not suggestions:
        return redirect("web_automation:new_product_step1")

    final_preview = None

    if request.method == "POST":
        form = ProductChoiceForm(request.POST, suggestions=suggestions)
        if form.is_valid():
            cleaned = form.cleaned_data

            def pick(choice_field, custom_field, key):
                custom_text = (cleaned.get(custom_field) or "").strip()
                if custom_text:
                    return custom_text
                idx_str = cleaned.get(choice_field)
                try:
                    idx = int(idx_str)
                except (TypeError, ValueError):
                    idx = 0
                items = suggestions.get(key, [])
                if 0 <= idx < len(items):
                    return items[idx]
                return items[0] if items else ""

            final_title = pick("title_choice", "custom_title", "titles")
            final_short = pick("short_desc_choice", "custom_short_desc", "short_descriptions")
            final_long = pick("long_desc_choice", "custom_long_desc", "long_descriptions")
            final_alt = pick("alt_text_choice", "custom_alt_text", "alt_texts")

            final_preview = {
                "title": final_title,
                "short_description": final_short,
                "long_description": final_long,
                "alt_text": final_alt,
            }

            # Store final copy in session for the next phase (Woo draft creation)
            request.session["new_product_final_copy"] = final_preview
            request.session.modified = True
    else:
        form = ProductChoiceForm(suggestions=suggestions)

    context = {
        "intake": intake,
        "form": form,
        "preview": final_preview,
    }
    return render(request, "web_automation/new_product_select.html", context)
def new_product_create_draft(request):
    """
    Step 4: Actually create the WooCommerce draft product using Pauly.
    - Requires: intake + final_copy in session.
    - Calls Pauly helper to create variable product + two matted variations.
    - Logs the run in AgentRun / AgentEvent.
    """
    if request.method != "POST":
        return redirect("web_automation:new_product_step1")

    intake = request.session.get("new_product_intake")
    final_copy = request.session.get("new_product_final_copy")

    if not intake or not final_copy:
        messages.error(
            request,
            "Missing product data. Please start again from the New Product Intake form.",
        )
        return redirect("web_automation:new_product_step1")

    run = AgentRun.objects.create(
        agent_name="Pauly",
        run_type="web",
        started_at=timezone.now(),
        status="running",
    )

    def log(level: str, message: str, extra=None):
        AgentEvent.objects.create(
            agent_run=run,
            timestamp=timezone.now(),
            level=level,
            message=message,
            extra=extra or {},
        )

    try:
        log("info", "Creating WooCommerce draft product via Website Automation Dashboard.")

        result = create_standard_print_product_from_web(
            intake=intake,
            final_copy=final_copy,
        )

        product = result.get("product", {}) or {}
        variations = result.get("variations", []) or []

        product_id = product.get("id")
        permalink = product.get("permalink")

        log(
            "info",
            f"Created draft product ID={product_id} with {len(variations)} variation(s).",
            extra={"product": product, "variations": variations},
        )

        run.status = "success"
        run.records_affected = 1 + len(variations)
        run.finished_at = timezone.now()
        run.save()

        context = {
            "product": product,
            "variations": variations,
            "permalink": permalink,
        }
        return render(request, "web_automation/new_product_created.html", context)

    except Exception as e:
        log("error", f"Error while creating WooCommerce draft product: {e}")
        run.status = "error"
        run.finished_at = timezone.now()
        run.save()
        messages.error(
            request,
            f"Error creating WooCommerce draft product: {e}",
        )
        return redirect("web_automation:new_product_select")

def seo_product_suggestions(request, product_id: int):
    """
    Show SamSEO suggestions for a single WooCommerce product.
    - Reads product from Woo
    - Generates focus keyphrase + meta description
    - Logs run in Automation Logs
    """
    run = AgentRun.objects.create(
        agent_name="SamSEO",
        run_type="web",
        started_at=timezone.now(),
        status="running",
    )

    def log(level: str, message: str, extra=None):
        AgentEvent.objects.create(
            agent_run=run,
            timestamp=timezone.now(),
            level=level,
            message=message,
            extra=extra or {},
        )

    try:
        log("info", f"Generating SEO suggestions for product ID={product_id}.")

        result = fetch_and_suggest_seo(product_id)
        product = result["product"]
        suggestions = result["suggestions"]

        run.status = "success"
        run.records_affected = 1
        run.finished_at = timezone.now()
        run.save()

        context = {
            "product": product,
            "suggestions": suggestions,
        }
        return render(request, "web_automation/seo_product_suggestions.html", context)

    except Exception as e:
        log("error", f"SamSEO failed for product ID={product_id}: {e}")
        run.status = "error"
        run.finished_at = timezone.now()
        run.save()

        messages.error(
            request,
            f"Error generating SEO suggestions: {e}",
        )
        return redirect("web_automation:dashboard")
    




def seo_product_lookup(request):
        """
        Simple form to enter a WooCommerce product ID and redirect to SamSEO suggestions.
        This MUST exist so urls.py can reference views.seo_product_lookup.
        """
        if request.method == "POST":
            form = SEOProductLookupForm(request.POST)
            if form.is_valid():
                product_id = form.cleaned_data["product_id"]
                url = reverse("web_automation:seo_product_suggestions", args=[product_id])
                return redirect(url)
        else:
            form = SEOProductLookupForm()

        return render(request, "web_automation/seo_product_lookup.html", {"form": form})

    
def mira_product_lookup(request):
    """
    Simple form to enter a WooCommerce product ID and redirect to Mira's blog draft.
    Reuses SEOProductLookupForm because it just asks for product_id.
    """
    if request.method == "POST":
        form = SEOProductLookupForm(request.POST)
        if form.is_valid():
            product_id = form.cleaned_data["product_id"]
            url = reverse("web_automation:mira_blog_suggestions", args=[product_id])
            return redirect(url)
    else:
        form = SEOProductLookupForm()

    return render(request, "web_automation/mira_product_lookup.html", {"form": form})


def mira_blog_suggestions(request, product_id: int):
    """
    Show Mira's blog draft + social caption for a single WooCommerce product.
    Logged to Automation Logs for traceability.
    """
    run = AgentRun.objects.create(
        agent_name="Mira",
        run_type="web",
        started_at=timezone.now(),
        status="running",
    )

    def log(level: str, message: str, extra=None):
        AgentEvent.objects.create(
            agent_run=run,
            timestamp=timezone.now(),
            level=level,
            message=message,
            extra=extra or {},
        )

    try:
        log("info", f"Generating blog draft for product ID={product_id}.")

        result = fetch_and_generate_blog(product_id)
        product = result["product"]
        blog = result["blog"]

        run.status = "success"
        run.records_affected = 1
        run.finished_at = timezone.now()
        run.save()

        context = {
            "product": product,
            "blog": blog,
        }
        return render(request, "web_automation/mira_blog_suggestions.html", context)

    except Exception as e:
        log("error", f"Mira failed for product ID={product_id}: {e}")
        run.status = "error"
        run.finished_at = timezone.now()
        run.save()

        messages.error(
            request,
            f"Error generating blog draft: {e}",
        )
        return redirect("web_automation:dashboard")
