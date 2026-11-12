# Artwork Inventory local test

This first version tracks P. Forbes Art originals and separately ordered, locally held prints. Print inventory is independent of WooCommerce and does not create website products. It does not connect to QuickBooks, Forbes Lawn, Jobber, or DigitalOcean data.

Before migrating, verify your local .env points to a local development database, not DigitalOcean or production.

From the project folder:
1. .venv\\Scripts\\python.exe manage.py migrate art_inventory
2. .venv\\Scripts\\python.exe manage.py test art_inventory
3. .venv\\Scripts\\python.exe manage.py runserver 8003
4. Open http://127.0.0.1:8003/admin/ and sign in, then open http://127.0.0.1:8003/inventory/.

The inventory has two separate entry actions. Add an original when you finish a painting. When you later order prints, choose Add print, select the artwork title, then select one of the three print formats. You can record a starting quantity and location, or leave the count at zero and use Record activity when the prints arrive.

Try a sample original, add one print size, then record a transfer to Images Art Gallery and a local sale. Confirm the counts change. A made-to-order website sale must leave the local print count unchanged. An original sale marks it sold and clears its location.

The automated tests need PostgreSQL permission to create a temporary test database. If your local role does not have that permission, test through the browser or ask for a temporary local test-database role grant. No production database is involved.
