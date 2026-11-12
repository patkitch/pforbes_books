# Artwork inventory local test

This first version is for P. Forbes Art inventory only. It does not connect to QuickBooks, Forbes Lawn, Jobber, WooCommerce, or DigitalOcean data.

Before migrating, verify your local .env points to a local development database, not DigitalOcean or production.

From the project folder:
1. python manage.py migrate
2. python manage.py test art_inventory
3. python manage.py runserver
4. Open http://127.0.0.1:8003/inventory/ and sign in with your local Django user.

Try a sample original, add an 8 x 10 print option, add 5 prints at Home, transfer 2 to Images Art Gallery, then record a local sale of 1. The counts should become 3 at Home and 1 at the gallery. A made-to-order sale should leave these physical counts unchanged. An original sale should mark the painting sold and clear its location.

These actions are local test data only. No WooCommerce product is created or changed.
