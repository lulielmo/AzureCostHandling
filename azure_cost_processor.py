import logging
from datetime import datetime, timedelta
from azure.identity import ClientSecretCredential, DefaultAzureCredential
from azure.mgmt.costmanagement import CostManagementClient
from azure.mgmt.resource import ResourceManagementClient
from azure.mgmt.costmanagement.models import (
    GenerateDetailedCostReportDefinition,
    GenerateDetailedCostReportTimePeriod,
    GenerateDetailedCostReportMetricType
)
import pandas as pd
import config
import time
import requests
import re

# Konfigurera loggning
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('azure_cost_processor.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class AzureCostProcessor:
    def __init__(self):
        self.credentials = ClientSecretCredential(
            tenant_id=config.AZURE_TENANT_ID,
            client_id=config.AZURE_CLIENT_ID,
            client_secret=config.AZURE_CLIENT_SECRET
        )
        self.cost_client = CostManagementClient(self.credentials)
        self.resource_client = ResourceManagementClient(self.credentials, config.AZURE_TENANT_ID)

    def _get_time_period(self):
        """
        Skapar tidsperiod för rapporten baserat på konfiguration.
        """
        end_date = datetime.now()
        if config.REPORT_TIME_PERIOD == "Last30Days":
            start_date = end_date - timedelta(days=30)
        elif config.REPORT_TIME_PERIOD == "Last7Days":
            start_date = end_date - timedelta(days=7)
        elif config.REPORT_TIME_PERIOD == "LastMonth":
            start_date = end_date.replace(day=1) - timedelta(days=1)
            start_date = start_date.replace(day=1)
        else:
            raise ValueError(f"Okänd tidsperiod: {config.REPORT_TIME_PERIOD}")

        return GenerateDetailedCostReportTimePeriod(
            start=start_date.strftime("%Y-%m-%d"),
            end=end_date.strftime("%Y-%m-%d")
        )

    def generate_detailed_cost_report_billing_account(self, billing_account_id):
        """
        Genererar en detaljerad kostnadsrapport för ett billing account.
        Args:
            billing_account_id (str): Billing account ID
        Returns:
            str: URL till den genererade rapporten
        """
        try:
            logger.info(f"Genererar detaljerad kostnadsrapport för billing account: {billing_account_id}")
            report_definition = GenerateDetailedCostReportDefinition(
                metric=GenerateDetailedCostReportMetricType.ACTUAL_COST,
                time_period=self._get_time_period()
            )
            scope = f"/providers/Microsoft.Billing/billingAccounts/{billing_account_id}"
            result = self.cost_client.generate_detailed_cost_report.begin_create_operation(
                scope=scope,
                parameters=report_definition
            )
            logger.info("Väntar på att rapporten ska genereras...")
            report_url = None
            # Extrahera Location-headern från initial response
            location_url = result._polling_method._initial_response.http_response.headers.get("Location")
            if not location_url:
                logger.error("Kunde inte hitta Location-headern i initialt svar. Kan inte fortsätta.")
                return None
            logger.info(f"Location-header (operationStatus-URL): {location_url}")
            match = re.search(r'/operationResults?/([\w-]+)', location_url)
            if match:
                operation_id = match.group(1)
            else:
                logger.error("Kunde inte extrahera operationId från Location-headern.")
                return None
            operation_result_url = f"https://management.azure.com/providers/Microsoft.Billing/billingAccounts/{billing_account_id}/providers/Microsoft.CostManagement/operationResults/{operation_id}?api-version=2021-10-01"
            # Polling loop
            while True:
                time.sleep(10)
                status = result.status()
                logger.info(f"Rapportstatus: {status}")
                if status in ["Succeeded", "Completed"]:
                    # Hämta access token
                    credential = DefaultAzureCredential()
                    token = credential.get_token("https://management.azure.com/.default").token
                    headers = {"Authorization": f"Bearer {token}"}
                    response = requests.get(operation_result_url, headers=headers)
                    logger.info(f"Svar från operationResult-URL: {response.text}")
                    if response.ok:
                        data = response.json()
                        report_url = data.get("properties", {}).get("downloadUrl")
                        if report_url:
                            logger.info(f"Download URL till rapporten: {report_url}")
                        else:
                            logger.warning("Ingen downloadUrl hittades i operationResult-svaret.")
                    else:
                        logger.warning(f"Kunde inte hämta operationResult: {response.status_code} {response.text}")
                    break
                elif status == "Failed":
                    raise Exception("Rapportgenerering misslyckades")
            if not report_url:
                logger.warning("Kunde inte hitta rapport-URL. Kontrollera loggen för operationResult-svaret.")
            else:
                logger.info(f"Rapport genererad framgångsrikt: {report_url}")
            return report_url
        except Exception as e:
            logger.error(f"Fel vid generering av detaljerad kostnadsrapport: {str(e)}")
            raise

    def process_cost_data(self, report_url):
        """
        Bearbetar kostnadsdata från den detaljerade rapporten.
        
        Args:
            report_url (str): URL till den genererade rapporten
        
        Returns:
            pd.DataFrame: Bearbetad data i konteringsformat
        """
        try:
            logger.info("Bearbetar kostnadsdata från detaljerad rapport")
            
            # Här kommer vi att implementera nedladdning och bearbetning av rapporten
            # Detta är en platshållare för nu
            
            return None
        except Exception as e:
            logger.error(f"Fel vid bearbetning av kostnadsdata: {str(e)}")
            raise

def main():
    try:
        processor = AzureCostProcessor()
        logger.info("Azure Cost Processor startad")
        
        if not config.AZURE_BILLING_ACCOUNT_ID:
            raise ValueError("AZURE_BILLING_ACCOUNT_ID måste anges i .env-filen")
            
        report_url = processor.generate_detailed_cost_report_billing_account(config.AZURE_BILLING_ACCOUNT_ID)
        
        if report_url:
            processed_data = processor.process_cost_data(report_url)
            logger.info("Kostnadsdata bearbetad framgångsrikt")
        
    except Exception as e:
        logger.error(f"Ett fel uppstod: {str(e)}")
        raise

if __name__ == "__main__":
    main() 