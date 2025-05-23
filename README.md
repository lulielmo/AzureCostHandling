# Azure Cost Processor

Ett Python-verktyg för att automatisera hantering av Azure-kostnadsrapporter och konvertering till konteringsformat.

## Funktioner

- Anslutning till Azure-tenant
- Generering av kostnadsrapporter
- Automatisk nedladdning av rapporter
- Konvertering till konteringsformat i Excel

## Dokumentation

Detta repository innehåller två huvudsakliga dokument:

- **README.md** (denna fil): Innehåller instruktioner för installation, konfiguration och grundläggande användning av verktyget.
- **[konteringsregler.md](konteringsregler.md)**: Innehåller detaljerade regler och instruktioner för hur kostnader ska konteras, inklusive taggningskonventioner i Azure.

## Installation

1. Klona detta repository
2. Skapa en virtuell miljö:
   ```bash
   python -m venv venv
   source venv/bin/activate  # På Windows: venv\Scripts\activate
   ```
3. Installera beroenden:
   ```bash
   pip install -r requirements.txt
   ```

## Skapa och konfigurera app-registrering (service principal)

1. **Skapa app-registrering**
   ```sh
   az ad app create --display-name "AzureCostExportAutomation"
   ```
2. **Skapa service principal**
   ```sh
   az ad sp create --id <Application (client) ID>
   ```
3. **Skapa client secret**
   ```sh
   az ad app credential reset --id <Application (client) ID> --append --display-name "CostExportSecret"
   ```
   Spara värdet på `password` (client secret)!
4. **Hämta Tenant ID**
   ```sh
   az account show --query tenantId -o tsv
   ```
5. **Hämta Object ID för service principal**
   ```sh
   az ad sp list --display-name "AzureCostExportAutomation" --query "[0].objectId" -o tsv
   ```
   (Eller hitta det i Enterprise applications i portalen.)
6. **Generera ett GUID för rolltilldelning**
   ```sh
   uuidgen
   ```
7. **Skapa en fil `body.json` med följande innehåll:**
   ```json
   {
     "properties": {
       "principalId": "<Object ID>",
       "principalTenantId": "<Tenant ID>",
       "roleDefinitionId": "/providers/Microsoft.Billing/billingAccounts/<BillingAccountId>/billingRoleDefinitions/24f8edb6-1668-4659-b5e2-40bb5f3a7d7e"
     }
   }
   ```
8. **Hämta access token**
   ```sh
   az account get-access-token --resource=https://management.azure.com --query accessToken -o tsv
   ```
9. **Tilldela rollen EnrollmentReader på billing account med REST-anrop:**
   ```sh
   curl -X PUT \
     -H "Authorization: Bearer <access_token>" \
     -H "Content-Type: application/json" \
     -d @body.json \
     "https://management.azure.com/providers/Microsoft.Billing/billingAccounts/<BillingAccountId>/billingRoleAssignments/<GUID>?api-version=2024-04-01"
   ```

## Konfiguration

Skapa en `.env`-fil i projektets rot med följande variabler:
```
AZURE_TENANT_ID=din_tenant_id
AZURE_CLIENT_ID=din_client_id
AZURE_CLIENT_SECRET=din_client_secret
```

## Användning

```python
python azure_cost_processor.py
```

## Säkerhet

- Använd aldrig produktionsnycklar i utvecklingsmiljön
- Hantera alla känsliga uppgifter via miljövariabler
- Följ principen om minsta behörighet för Azure-behörigheter 