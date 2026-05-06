import os
import django
from django.template.loader import render_to_string
from django.conf import settings

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'eti_mis.settings')
django.setup()

try:
    # We just want to parse the template, rendering with an empty context
    render_to_string('accounts/bank_transactions.html', {})
    print("Template parsed successfully!")
except Exception as e:
    import traceback
    traceback.print_exc()
