import os
from dotenv import load_dotenv

# Ladda miljövariabler från .env-fil
load_dotenv()

# Azure-konfiguration
AZURE_TENANT_ID = os.getenv('AZURE_TENANT_ID')
AZURE_CLIENT_ID = os.getenv('AZURE_CLIENT_ID')
AZURE_CLIENT_SECRET = os.getenv('AZURE_CLIENT_SECRET')
AZURE_BILLING_ACCOUNT_ID = os.getenv('AZURE_BILLING_ACCOUNT_ID')

# Rapportkonfiguration
REPORT_TIME_PERIOD = "Last30Days"  # Kan ändras till "Last7Days", "LastMonth", etc.
REPORT_GRANULARITY = "Daily"  # Kan ändras till "Monthly", "Hourly", etc.

# Excel-konfiguration
EXCEL_OUTPUT_DIR = "reports"
EXCEL_TEMPLATE_PATH = "templates/accounting_template.xlsx"

# Skapa output-katalog om den inte finns
os.makedirs(EXCEL_OUTPUT_DIR, exist_ok=True) 