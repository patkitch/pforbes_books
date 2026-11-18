# Images Art Gallery Featured Artist Sign-ups

This section is an independent Django app mounted at `/gallery-signups/`. It has no links into the P. Forbes dashboards and stores only event/slot data, a hashed shared member password, and separate gallery assistant accounts.

## First setup

1. Apply database migrations: `python manage.py migrate`. The migration creates the 12 2027 third-Friday events and two spots for each.
2. Sign in to `/gallery-signups/manage/login/` with the existing Django superuser account. A Django superuser is the owner; create one with `python manage.py createsuperuser` if needed.
3. Open **Member password** and set the shared password. This password is hashed in the database.
4. Add assistant accounts under **Administrators**. Each assistant uses a separate username/password and can manage slots, but cannot change the member password or add administrators.

Members open `/gallery-signups/`, enter the shared password, and claim an open spot with their name. Contact information is not collected. Use **Clear spot** to remove a name, **Reserved for** to block a spot (for example, Juried Show), or close a whole month.

Admin password hashes and the member password are never stored in source code. No database, email, or third-party scheduling credentials are required by this feature.
