# Gallery signup deployment notes

This page describes the DigitalOcean settings needed before deploying the guest artist application form.

## Existing Spaces bucket

Use the existing `pforbesbooks-reports` bucket in the `nyc3` region. The app writes new application images beneath:

`gallery-signups/guest_artist_applications/<year>/...`

The Django storage backend requests signed URLs for images, so the bucket must remain private. Do not enable public read access for the bucket or its objects. The existing report objects are separate from this folder.

Create or use Spaces access keys and set these App Platform environment variables on the `pforbes-books` web service:

- `SPACES_BUCKET_NAME=pforbesbooks-reports`
- `SPACES_REGION_NAME=nyc3`
- `SPACES_ENDPOINT_URL=https://nyc3.digitaloceanspaces.com`
- `SPACES_ACCESS_KEY_ID` (secret)
- `SPACES_SECRET_ACCESS_KEY` (secret)

Do not put access keys in GitHub, this file, or chat.

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
