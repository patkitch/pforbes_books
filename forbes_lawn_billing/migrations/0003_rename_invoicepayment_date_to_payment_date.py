from django.db import migrations

SQL_RENAME = """
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name='forbes_lawn_billing_invoicepayment'
          AND column_name='date'
    )
    AND NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name='forbes_lawn_billing_invoicepayment'
          AND column_name='payment_date'
    )
    THEN
        ALTER TABLE forbes_lawn_billing_invoicepayment
        RENAME COLUMN date TO payment_date;
    END IF;
END $$;
"""

SQL_REVERSE = """
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name='forbes_lawn_billing_invoicepayment'
          AND column_name='payment_date'
    )
    AND NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name='forbes_lawn_billing_invoicepayment'
          AND column_name='date'
    )
    THEN
        ALTER TABLE forbes_lawn_billing_invoicepayment
        RENAME COLUMN payment_date TO date;
    END IF;
END $$;
"""

class Migration(migrations.Migration):

    dependencies = [
        ("forbes_lawn_billing", "0002_alter_invoice_customer_name_and_more"),
    ]

    operations = [
        migrations.RunSQL(SQL_RENAME, reverse_sql=SQL_REVERSE),
    ]
