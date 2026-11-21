# Gallery signup deployment notes

This page describes the DigitalOcean settings needed before deploying the guest artist application form.

## Existing Spaces bucket

Use the existing private `pforbesbooks-reports` bucket in the `nyc3` region. The app reads the existing DigitalOcean environment variables already shown in App Platform:

- `DO_SPACES_BUCKET`
- `DO_SPACES_KEY`
- `DO_SPACES_SECRET`
- `DO_SPACES_REGION`
- `DO_SPACES_ENDPOINT`
- `DO_SPACES_USE_HTTPS`
- `DO_SPACES_ADDRESSING_STYLE` (if present)

The signup app maps these existing names automatically, so there is no need to add duplicate `SPACES_*` credentials. It writes new application images beneath:

`gallery-signups/guest_artist_applications/<year>/...`

Keep the bucket private. The Django storage backend requests signed URLs for images; do not enable public read access for the bucket or its objects. Existing report objects are separate from this folder. Before deployment, confirm the values above are set on the web service and that the bucket is private.

## Titan email

Set these App Platform environment variables:

- `EMAIL_HOST=smtp.titan.email`
- `EMAIL_PORT=587`
- `EMAIL_USE_TLS=True`
- `EMAIL_USE_SSL=False`
- `EMAIL_HOST_USER` (the Titan mailbox used to send gallery email)
- `EMAIL_HOST_PASSWORD` (secret; use the mailbox or app password Titan requires)
- `DEFAULT_FROM_EMAIL` (a sender address authorized by Titan)
- `GALLERY_ADMIN_EMAIL=patriciaforbes@pforbesart.com`

Do not put mailbox credentials in GitHub, this file, or chat.

## Release steps

1. Confirm the existing bucket is private and configure the environment variables above in DigitalOcean App Platform.
2. Merge the signup pull request to `main`, which triggers the existing App Platform deployment.
3. In the App Platform component console, run:

   `python manage.py migrate`

   This applies `gallery_signups.0003_applications_signup_history` for application records, submitted images, and signup history.
4. Confirm the deployment completes, then verify member login/calendar, public guest calendar/application, admin review, email delivery, and private image access.

If the Spaces or Titan credentials are not configured, image uploads or email delivery will not work. The form allows an artwork URL as an alternative to image uploads.
