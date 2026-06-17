# Azure Cost Processor

Ett Python-verktyg för att automatisera hantering av Azure-kostnadsrapporter och konvertering till konteringsformat.

## Bakgrund och syfte

Azurefakturan vi får från Atea innehåller normalt inte tillräcklig detaljinformation om **vilka Azure-tjänster/resurser** som nyttjats eller **vad respektive nyttjande kostat**. Det här verktyget laddar därför ner en detaljerad kostnadsrapport från Azure Cost Management och **analyserar raderna** för att skapa **konteringsrader** som kan klistras in/importeras i vårt fakturahanteringssystem (Medius).

Gruppering och kontering styrs primärt av **konfigurerbara regler i JSON** (resourceId-wildcards), med en särskild hantering för Azure DevOps samt en uppsamlingskontering för rader som ännu saknar matchande regel.

## Funktioner

- Anslutning till Azure-tenant
- Generering av kostnadsrapporter
- Automatisk nedladdning av rapporter
- Konvertering till konteringsformat i Excel
- **Central styrning av konteringsregler via kontering_resource_config.json**

## Viktigt om konteringsregler

> **OBS!** Du behöver inte längre tagga resurser i Azure för konteringssyfte. All gruppering och kontering styrs nu via mönster (wildcards) på ResourceId i filen `kontering_resource_config.json`.
>
> Se [konteringsregler.md](konteringsregler.md) för detaljerade instruktioner och exempel på hur du klumpar ihop kostnader baserat på sökvägar i ResourceId.

## Dokumentation

Detta repository innehåller två huvudsakliga dokument:

- **README.md** (denna fil): Innehåller instruktioner för installation, konfiguration och grundläggande användning av verktyget.
- **[konteringsregler.md](konteringsregler.md)**: Innehåller detaljerade regler och instruktioner för hur kostnader ska konteras, inklusive hur du arbetar med resourceId-mönster.

## Installation

1. Klona detta repository
2. Installera [uv](https://docs.astral.sh/uv/) (t.ex. `winget install astral-sh.uv`)
3. Synka projektets virtuella miljö och beroenden:
   ```bash
   uv sync
   ```

uv läser Python-versionen från `.python-version` (3.14) och installerar exakta paketversioner från `uv.lock`.

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

```bash
uv run python azure_cost_processor.py
```

## Beroendehantering

```bash
# Lägg till ett nytt paket
uv add paketnamn

# Uppgradera alla beroenden
uv lock --upgrade && uv sync

# Uppgradera ett specifikt paket
uv lock --upgrade-package pandas && uv sync
```

## Säkerhet

- Använd aldrig produktionsnycklar i utvecklingsmiljön
- Hantera alla känsliga uppgifter via miljövariabler
- Följ principen om minsta behörighet för Azure-behörigheter 