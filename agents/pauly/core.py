import os
from typing import List, Dict, Tuple, Any, Optional
import mimetypes
import requests
from dotenv import load_dotenv


# Load variables from .env when running locally.
load_dotenv()
WOO_BASE_URL = os.getenv("WOO_BASE_URL", "").rstrip("/")
WOO_CONSUMER_KEY = os.getenv("WOO_CONSUMER_KEY", "")
WOO_CONSUMER_SECRET = os.getenv("WOO_CONSUMER_SECRET", "")


def get_woo_config():
    """
    Reads WooCommerce connection info from environment variables.
    """
    base_url = os.getenv("WOO_BASE_URL")
    consumer_key = os.getenv("WOO_CONSUMER_KEY")
    consumer_secret = os.getenv("WOO_CONSUMER_SECRET")

    if not base_url or not consumer_key or not consumer_secret:
        raise RuntimeError(
            "WooCommerce configuration is incomplete. "
            "Check WOO_BASE_URL, WOO_CONSUMER_KEY, WOO_CONSUMER_SECRET."
        )

    # Normalize base URL (remove trailing slash)
    base_url = base_url.rstrip("/")

    return {
        "base_url": base_url,
        "consumer_key": consumer_key,
        "consumer_secret": consumer_secret,
    }

# Canonical variation template for P.Forbes Art prints.
# Harold v1: standardize on a single attribute "Size"
# with two options: "11x14 white mat" and "8x10 white mat".

STANDARD_PRINT_ATTRIBUTE_NAME = "Size"
STANDARD_PRINT_ATTRIBUTE_SLUG = "pa_size"  # Woo will usually slugify "Size" like this
STANDARD_PRINT_TITLE_SUFFIX = " – Open Edition Giclée Matted Print by P. Forbes"
STANDARD_PRINT_VARIATIONS = [
    "11x14 white mat",
    "8x10 white mat",
]
STANDARD_PRINT_PRICING = {
    "11x14 white mat": "45.00",
    "8x10 white mat": "20.00",
}

def inspect_product_for_standard_print(product: dict) -> dict:
    """
    Inspect a WooCommerce product and report whether it matches
    the STANDARD_PRINT_* template.

    Returns a dict like:
    {
        "id": 123,
        "name": "...",
        "type": "simple" | "variable" | ...,
        "is_standard": True/False,
        "reason": "..."  # if not standard
    }
    """
    pid = product.get("id")
    name = product.get("name")
    ptype = product.get("type")

    # We only care about variable products for this template
    if ptype != "variable":
        return {
            "id": pid,
            "name": name,
            "type": ptype,
            "is_standard": False,
            "reason": f"Product type is '{ptype}', expected 'variable'.",
        }

    attributes = product.get("attributes", [])
    size_attr = None

    for attr in attributes:
        # Woo often uses 'name' and 'slug'
        if (
            attr.get("name") == STANDARD_PRINT_ATTRIBUTE_NAME
            or attr.get("slug") == STANDARD_PRINT_ATTRIBUTE_SLUG
        ):
            size_attr = attr
            break

    if not size_attr:
        return {
            "id": pid,
            "name": name,
            "type": ptype,
            "is_standard": False,
            "reason": "No 'Size' attribute found.",
        }

    options = size_attr.get("options", []) or []

    missing = [v for v in STANDARD_PRINT_VARIATIONS if v not in options]
    extra = [opt for opt in options if opt not in STANDARD_PRINT_VARIATIONS]

    if missing or extra:
        details = []
        if missing:
            details.append(f"missing: {', '.join(missing)}")
        if extra:
            details.append(f"extra: {', '.join(extra)}")
        reason = "; ".join(details)
        return {
            "id": pid,
            "name": name,
            "type": ptype,
            "is_standard": False,
            "reason": f"Size attribute options don't match template ({reason}).",
        }

    return {
        "id": pid,
        "name": name,
        "type": ptype,
        "is_standard": True,
        "reason": "Matches STANDARD_PRINT template.",
    }



def woo_get(endpoint: str, params: Dict = None) -> Dict:
    """
    Performs a READ-ONLY GET request to the WooCommerce REST API.

    endpoint: the path after /wp-json/wc/v3/, e.g. "products"
    params: optional query parameters
    """
    cfg = get_woo_config()

    url = f"{cfg['base_url']}/wp-json/wc/v3/{endpoint}"

    # Always include auth params
    params = params.copy() if params else {}
    params.update({
        "consumer_key": cfg['consumer_key'],
        "consumer_secret": cfg['consumer_secret'],
    })

    response = requests.get(url, params=params, timeout=15)

    if not response.ok:
        raise RuntimeError(
            f"WooCommerce API GET {endpoint} failed "
            f"with status {response.status_code}: {response.text}"
        )

    return response.json()


def test_woocommerce_connection(max_products: int = 5) -> List[Dict]:
    """
    Simple READ-ONLY test:
    - Fetches up to `max_products` products from WooCommerce.
    - Returns a list of dicts with id, name, status for logging.
    """
    products = woo_get("products", params={"per_page": max_products})

    summary = []
    for p in products:
        summary.append({
            "id": p.get("id"),
            "name": p.get("name"),
            "status": p.get("status"),
        })

    return summary


# -------------------------------------------------------------------
# Pauly's product payload builder (no network calls here)
# -------------------------------------------------------------------

def build_variable_product_payload(artwork: Dict) -> Tuple[Dict, List[Dict]]:
    """
    Given a description of a new artwork, build:
    - the parent variable product payload
    - the two variation payloads (11x14 white mat, 8x10 white mat)

    This DOES NOT send anything to WooCommerce.
    It just returns the JSON-ready dicts.
    """

    # Fixed size labels for your shop
    size_11x14 = "11x14 white mat"
    size_8x10 = "8x10 white mat"

    title = artwork["title"]
    short_description = artwork["short_description"]
    long_description = artwork["description_long"]
    sku_base = artwork["sku_base"]
    price_11x14 = artwork["price_11x14"]
    price_8x10 = artwork["price_8x10"]

    categories = []
    tags = artwork.get("tags", [])

    # Woo expects categories/tags as list of objects: {"name": "Category Name"}
    category_objects = [{"name": name} for name in categories]
    tag_objects = [{"name": name} for name in tags]

    # Parent product payload (variable, draft)
    product_payload = {
        "name": title,
        "type": "variable",
        "status": "draft",  # Always draft for safety
        "description": long_description,        # full story, can be HTML
        "short_description": short_description, # listing blurb
        "sku": sku_base,                        # base SKU for the parent
        "categories": category_objects,
        "tags": tag_objects,
        "attributes": [
            {
                "name": "Size",
                "position": 0,
                "visible": True,
                "variation": True,  # used for variations
                "options": [size_11x14, size_8x10],
            }
        ],
        # We will attach images later when we wire up image upload
    }

    # Variation payloads (not sent yet)
    variations_payload = [
        {
            "regular_price": price_11x14,
            "sku": f"{sku_base}-11x14",
            "attributes": [
                {
                    "name": "Size",
                    "option": size_11x14,
                }
            ],
        },
        {
            "regular_price": price_8x10,
            "sku": f"{sku_base}-8x10",
            "attributes": [
                {
                    "name": "Size",
                    "option": size_8x10,
                }
            ],
        },
    ]

    return product_payload, variations_payload

def woo_post(endpoint: str, payload: Dict) -> Dict:
    """
    Performs a POST request to the WooCommerce REST API.

    Used for creating products, variations, etc.
    """
    cfg = get_woo_config()

    url = f"{cfg['base_url']}/wp-json/wc/v3/{endpoint}"

    params = {
        "consumer_key": cfg['consumer_key'],
        "consumer_secret": cfg['consumer_secret'],
    }

    response = requests.post(url, json=payload, params=params, timeout=20)

    if not response.ok:
        raise RuntimeError(
            f"WooCommerce API POST {endpoint} failed "
            f"with status {response.status_code}: {response.text}"
        )

    return response.json()




def _get_category_id_by_name(name: str) -> Optional[int]:
    """
    Look up a WooCommerce product category ID by its name.
    Used to find 'Giclée prints' so new products land in the right bucket.
    """
    try:
        categories = woo_get("products/categories", params={"per_page": 100})
    except Exception:
        return None

    for cat in categories:
        if cat.get("name") == name:
            return cat.get("id")
    return None


def create_standard_print_product_from_web(
    intake: Dict[str, Any],
    final_copy: Dict[str, str],
) -> Dict[str, Any]:
    """
    Create a new variable WooCommerce product (draft) for a matted Giclée print
    using data collected from the Website Automation Dashboard.

    - intake: data from NewProductForm (title, image_url, media_id, etc.)
    - final_copy: chosen title/short/long/alt from Step 3.
    """

    title = final_copy.get("title", "").strip() or intake.get("title", "").strip()
    short_description = final_copy.get("short_description", "").strip()
    long_description = final_copy.get("long_description", "").strip()
    alt_text = final_copy.get("alt_text", "").strip()

    image_url = (intake.get("image_url") or "").strip()
    # We ignore media_id for now and just use the image URL

    # Find the 'Giclée prints' category ID if it exists
    giclee_cat_id = _get_category_id_by_name("Giclée prints")

    categories: List[Dict[str, Any]] = []
    if giclee_cat_id:
        categories.append({"id": giclee_cat_id})

    images: List[Dict[str, Any]] = []
    if image_url:
        images.append(
            {
                "src": image_url,
                "alt": alt_text or title,
            }
        )

    # Standard matted variations
    attributes = [
        {
            "name": "Size",
            "visible": True,
            "variation": True,
            "options": [
                "11x14 white mat",
                "8x10 white mat",
            ],
        }
    ]

    product_payload: Dict[str, Any] = {
        "name": title,
        "type": "variable",
        "status": "draft",
        "description": long_description,
        "short_description": short_description,
        "categories": categories,
        "images": images,
        "attributes": attributes,
    }

    # Create the variable product itself
    product = woo_post("products", product_payload)
    product_id = product.get("id")

    # Create the two size variations
    variation_payloads = [
        {
            "regular_price": "45.00",
            "attributes": [
                {"name": "Size", "option": "11x14 white mat"},
            ],
        },
        {
            "regular_price": "20.00",
            "attributes": [
                {"name": "Size", "option": "8x10 white mat"},
            ],
        },
    ]

    created_variations: List[Dict[str, Any]] = []
    for payload in variation_payloads:
        v = woo_post(f"products/{product_id}/variations", payload)
        created_variations.append(v)

    return {
        "product": product,
        "variations": created_variations,
    }






def convert_simple_product_to_standard_print(product_id: int, dry_run: bool = True) -> Dict[str, Any]:
    """
    Convert a single simple WooCommerce product into a new variable product
    that matches the STANDARD_PRINT template.

    - Does NOT modify or delete the original product.
    - Creates a NEW product with type='variable' and status='draft'.
    - Creates one variation per value in STANDARD_PRINT_VARIATIONS, using
      STANDARD_PRINT_PRICING when available, or falling back to the original
      simple product's regular_price.

    If dry_run=True, it only returns a plan dict describing what it WOULD do.
    If dry_run=False, it performs the API calls and returns a result summary.
    """
    # 1. Fetch the original product
    original = woo_get(f"products/{product_id}")
    if not original:
        raise ValueError(f"No product found with ID={product_id}")

    if original.get("type") != "simple":
        raise ValueError(
            f"Product ID={product_id} is type '{original.get('type')}', expected 'simple'."
        )

    # 2. Determine base price (used only as fallback)
    base_price = original.get("regular_price") or original.get("sale_price")
    if not base_price:
        base_price = "0.00"

    name = original.get("name") or ""
    description = original.get("description") or ""
    short_description = original.get("short_description") or ""
    categories = original.get("categories", []) or []
    images = original.get("images", []) or []
    tags = original.get("tags", []) or []

    # Try to recover the "artwork title" (strip old suffixes like size / giclée)
    artwork_title = name
    if "–" in artwork_title:
        # Use the part before the en dash
        artwork_title = artwork_title.split("–")[0].strip()
    elif "|" in artwork_title:
        # Fallback: if title uses pipes, take the first segment
        artwork_title = artwork_title.split("|")[0].strip()

    # Pat's chosen standard title format (Option B)
    name = f"{artwork_title} {STANDARD_PRINT_TITLE_SUFFIX}"

    # Pat's chosen standard short description (Option B)
    short_description = (
        "Open Edition matted Giclée print of an original acrylic painting – Two Sizes"
    )
    # 3. Build the payload for the new variable product
    new_product_payload: Dict[str, Any] = {
        "name": name,
        "type": "variable",
        "status": "draft",
        "description": description,
        "short_description": short_description,
        "categories": categories,
        "images": images,
        "tags": tags,  # preserve any existing tags
        "attributes": [
            {
                "name": STANDARD_PRINT_ATTRIBUTE_NAME,
                "slug": STANDARD_PRINT_ATTRIBUTE_SLUG,
                "visible": True,
                "variation": True,
                "options": STANDARD_PRINT_VARIATIONS,
            }
        ],
    }

    # 4. Build the variation payloads (one per size)
    variation_payloads: List[Dict[str, Any]] = []
    for option in STANDARD_PRINT_VARIATIONS:
        # Use fixed pricing when defined, otherwise fall back to base_price
        price = STANDARD_PRINT_PRICING.get(option, str(base_price))

        variation_payloads.append(
            {
                "regular_price": str(price),
                "attributes": [
                    {
                        "name": STANDARD_PRINT_ATTRIBUTE_NAME,
                        "option": option,
                    }
                ],
            }
        )

    plan = {
        "original_product_id": product_id,
        "original_name": name,
        "original_price": base_price,
        "new_product_payload": new_product_payload,
        "variation_payloads": variation_payloads,
    }

    if dry_run:
        return {
            "original": original,
            "plan": plan,
        }

    # 5. Actually create the variable product
    created_product = woo_post("products", new_product_payload)
    new_id = created_product.get("id")

    if not new_id:
        raise RuntimeError("Failed to create new variable product; no ID returned.")

    created_variations: List[Dict[str, Any]] = []
    for vp in variation_payloads:
        v = woo_post(f"products/{new_id}/variations", vp)
        created_variations.append(v)

    return {
        "original": original,
        "plan": plan,
        "created_product": created_product,
        "created_variations": created_variations,
    }




def create_variable_product_draft(artwork: Dict) -> Dict:
    """
    FULL RUN (real write):

    - Builds the parent variable product payload
    - Creates the parent product in WooCommerce as DRAFT
    - Creates two variations (11x14 and 8x10 white mat)
    - Returns a summary with product and variations data

    NOTE: This function DOES talk to WooCommerce and creates real objects
    as draft. Use it only when you're ready.
    """
    # 1) Build the payloads
    product_payload, variations_payload = build_variable_product_payload(artwork)

    # 2) Create parent product (draft) in WooCommerce
    product_response = woo_post("products", product_payload)
    product_id = product_response.get("id")

    if not product_id:
        raise RuntimeError("WooCommerce did not return a product ID for the created product.")

    # 3) Create variations under this product
    created_variations = []
    for var_payload in variations_payload:
        var_response = woo_post(f"products/{product_id}/variations", var_payload)
        created_variations.append(var_response)

    return {
        "product": product_response,
        "variations": created_variations,
    }
def upload_image_to_wordpress(image_path: str, title: str | None = None, alt_text: str | None = None) -> dict:
    """
    Upload a local image file to WordPress media library using the REST API.
    Returns the created media JSON (including 'id' and 'source_url').

    This does NOT attach it to a product yet; it's just an upload.
    """
    if not WOO_BASE_URL or not WOO_CONSUMER_KEY or not WOO_CONSUMER_SECRET:
        raise RuntimeError("WooCommerce/WordPress environment variables are not set.")


    if not os.path.isfile(image_path):
        raise FileNotFoundError(f"Image file not found: {image_path}")

    media_url = f"{WOO_BASE_URL}/wp-json/wp/v2/media"

    filename = os.path.basename(image_path)
    mime_type, _ = mimetypes.guess_type(filename)
    if mime_type is None:
        # Fallback to jpeg if unknown
        mime_type = "image/jpeg"

    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
    }

    data = {}
    if title:
        data["title"] = title
    if alt_text:
        data["alt_text"] = alt_text

    with open(image_path, "rb") as f:
        files = {
            "file": (filename, f, mime_type),
        }

        response = requests.post(
            media_url,
            auth=(WOO_CONSUMER_KEY, WOO_CONSUMER_SECRET),
            headers=headers,
            data=data,
            files=files,
            timeout=30,
        )

    response.raise_for_status()
    return response.json()