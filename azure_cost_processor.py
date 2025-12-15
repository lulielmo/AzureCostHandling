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
import os
import argparse
import json
import glob
import re

# Konfigurera loggning
def setup_logging(verbose=False):
    # Stäng av HTTP-loggning från Azure SDK om inte verbose-läge är aktiverat
    if not verbose:
        logging.getLogger('azure.core.pipeline.policies.http_logging_policy').setLevel(logging.WARNING)
        logging.getLogger('azure.identity').setLevel(logging.WARNING)
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('azure_cost_processor.log'),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)

class AzureCostProcessor:
    def __init__(self, logger):
        self.logger = logger
        self.credentials = ClientSecretCredential(
            tenant_id=config.AZURE_TENANT_ID,
            client_id=config.AZURE_CLIENT_ID,
            client_secret=config.AZURE_CLIENT_SECRET
        )
        self.cost_client = CostManagementClient(self.credentials)
        self.resource_client = ResourceManagementClient(self.credentials, config.AZURE_TENANT_ID)

    def _get_time_period(self, billing_period=None):
        """
        Skapar tidsperiod för rapporten baserat på konfiguration eller angiven period (YYYYMM).
        Args:
            billing_period (str, optional): Period i formatet 'YYYYMM'
        Returns:
            GenerateDetailedCostReportTimePeriod
        """
        if billing_period:
            # Omvandla YYYYMM till start och slut på månaden
            try:
                start_date = datetime.strptime(billing_period, "%Y%m")
                # Sista dagen i månaden: ta första dagen i nästa månad minus en dag
                if start_date.month == 12:
                    next_month = start_date.replace(year=start_date.year+1, month=1, day=1)
                else:
                    next_month = start_date.replace(month=start_date.month+1, day=1)
                end_date = next_month - timedelta(days=1)
            except Exception as e:
                raise ValueError(f"Felaktigt format på period: {billing_period}. Ange som 'YYYYMM'.")
        else:
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

    def generate_detailed_cost_report_billing_account(self, billing_account_id, billing_period=None):
        """
        Genererar en detaljerad kostnadsrapport för ett billing account.
        Args:
            billing_account_id (str): Billing account ID
            billing_period (str, optional): Period i formatet 'YYYYMM'
        Returns:
            str: URL till den genererade rapporten
        """
        try:
            self.logger.info(f"Genererar detaljerad kostnadsrapport för billing account: {billing_account_id}")
            report_definition = GenerateDetailedCostReportDefinition(
                metric=GenerateDetailedCostReportMetricType.ACTUAL_COST,
                time_period=self._get_time_period(billing_period)
            )
            scope = f"/providers/Microsoft.Billing/billingAccounts/{billing_account_id}"
            result = self.cost_client.generate_detailed_cost_report.begin_create_operation(
                scope=scope,
                parameters=report_definition
            )
            self.logger.info("Väntar på att rapporten ska genereras...")
            report_url = None
            # Extrahera Location-headern från initial response
            location_url = result._polling_method._initial_response.http_response.headers.get("Location")
            if not location_url:
                self.logger.error("Kunde inte hitta Location-headern i initialt svar. Kan inte fortsätta.")
                return None
            if self.logger.level == logging.DEBUG:
                self.logger.info(f"Location-header (operationStatus-URL): {location_url}")
            else:
                self.logger.info("Location-header mottagen (operationStatus-URL).")
            match = re.search(r'/operationResults?/([\w-]+)', location_url)
            if match:
                operation_id = match.group(1)
            else:
                self.logger.error("Kunde inte extrahera operationId från Location-headern.")
                return None
            operation_result_url = f"https://management.azure.com/providers/Microsoft.Billing/billingAccounts/{billing_account_id}/providers/Microsoft.CostManagement/operationResults/{operation_id}?api-version=2021-10-01"
            # Polling loop
            while True:
                time.sleep(10)
                status = result.status()
                self.logger.info(f"Rapportstatus: {status}")
                if status in ["Succeeded", "Completed"]:
                    # Hämta access token
                    credential = DefaultAzureCredential()
                    token = credential.get_token("https://management.azure.com/.default").token
                    headers = {"Authorization": f"Bearer {token}"}
                    response = requests.get(operation_result_url, headers=headers)
                    if self.logger.level == logging.DEBUG:
                        self.logger.info(f"Svar från operationResult-URL: {response.text}")
                    else:
                        self.logger.info("Svar mottaget från operationResult-URL.")
                    if response.ok:
                        data = response.json()
                        report_url = data.get("properties", {}).get("downloadUrl")
                        if report_url:
                            if self.logger.level == logging.DEBUG:
                                self.logger.info(f"Download URL till rapporten: {report_url}")
                            else:
                                self.logger.info("Download URL till rapporten mottagen.")
                        else:
                            self.logger.warning("Ingen downloadUrl hittades i operationResult-svaret.")
                    else:
                        self.logger.warning(f"Kunde inte hämta operationResult: {response.status_code} {response.text}")
                    break
                elif status == "Failed":
                    raise Exception("Rapportgenerering misslyckades")
            if not report_url:
                self.logger.warning("Kunde inte hitta rapport-URL. Kontrollera loggen för operationResult-svaret.")
            else:
                if self.logger.level == logging.DEBUG:
                    self.logger.info(f"Rapport genererad framgångsrikt: {report_url}")
                else:
                    self.logger.info("Rapport genererad framgångsrikt.")
            return report_url
        except Exception as e:
            self.logger.error(f"Fel vid generering av detaljerad kostnadsrapport: {str(e)}")
            raise

    def extract_tags(self, row):
        # Standardvärden
        row['BillingTag'] = ''
        row['CostCenterTag'] = ''
        row['BillingRGTag'] = ''
        row['BillingProjTag'] = ''
        row['BillingAktTag'] = ''
        row['BillingKatTag'] = ''
        row['BillingDescriptionTag'] = ''

        # Hämta Tags och kontrollera att det är en giltig sträng
        tags = row.get('Tags', '')
        if pd.isna(tags) or not isinstance(tags, str):
            return row

        # Försök tolka som JSON
        try:
            tag_dict = json.loads(tags.replace("'", '"'))
            # Hantera olika möjliga nycklar (case-insensitive)
            for k, v in tag_dict.items():
                key = k.lower()
                if key == 'billing':
                    row['BillingTag'] = str(v)
                elif key == 'costcenter':
                    row['CostCenterTag'] = str(v)
                elif key == 'billing-rg':
                    row['BillingRGTag'] = str(v)
                elif key == 'billing-proj':
                    row['BillingProjTag'] = str(v)
                elif key == 'billing-akt':
                    row['BillingAktTag'] = str(v)
                elif key == 'billing-kat':
                    row['BillingKatTag'] = str(v)
                elif key == 'billing-description':
                    row['BillingDescriptionTag'] = str(v)
        except Exception:
            # Fallback: regex för "key": "value"
            def extract_regex(tag, s):
                try:
                    import re
                    match = re.search(rf'"{tag}"\s*:\s*"([^"]+)"', s, re.IGNORECASE)
                    return match.group(1) if match else ''
                except Exception:
                    return ''
            row['BillingTag'] = extract_regex('Billing', tags)
            row['CostCenterTag'] = extract_regex('costcenter', tags)
            row['BillingRGTag'] = extract_regex('Billing-RG', tags)
            row['BillingProjTag'] = extract_regex('Billing-proj', tags)
            row['BillingAktTag'] = extract_regex('Billing-akt', tags)
            row['BillingKatTag'] = extract_regex('Billing-kat', tags)
            row['BillingDescriptionTag'] = extract_regex('Billing-description', tags)
        return row

    def load_resource_kontering_config(self, path="kontering_resource_config.json"):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f).get("konteringsregler", [])
        except Exception as e:
            self.logger.info(f"Kunde inte läsa konteringsregler: {e}")
            return []

    def hitta_konteringsregel(self, resource_id, regler):
        for regel in regler:
            for pattern in regel.get("resource_ids", []):
                if glob.fnmatch.fnmatch(str(resource_id).lower(), str(pattern).lower()):
                    return regel
        return None

    def load_kontering_config(self, path="kontering_config.json"):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            self.logger.warning(f"Kunde inte läsa konteringskonfiguration: {e}. Använder standardvärden.")
            # Fallback till hårdkodade värden om filen saknas
            return {
                "uppsamlingskontering": {
                    "konproj": "P.201726",
                    "rg": "",
                    "akt": "999",
                    "projkat": "5420"
                },
                "devops": {
                    "konproj": "9999",
                    "rg": "",
                    "akt": "",
                    "projkat": ""
                },
                "godkant_av": "John Munthe"
            }

    def generate_konteringsrader(self, df, config):
        rows = []
        warnings = []
        resource_kontering_regler = self.load_resource_kontering_config()

        def build_kontering_row(kontering_src, belopp, kommentar, godkant_av):
            """
            Bygger en konteringsrad enligt reglerna:
            - Endast en av rg eller konproj ska vara satt per rad.
            - Om båda är satta: logga varning, men behandla raden som projektkontering.
            - Om rg är satt (rörelsegrenskontering):
                RG = rg
                Kon/Proj = projkat
                ProjKat lämnas tom
            - Om konproj är satt (projektkontering):
                Kon/Proj = konproj
                ProjKat = projkat
                RG lämnas tom
            """
            konproj_val = str(kontering_src.get("konproj", "") or "").strip()
            rg_val = str(kontering_src.get("rg", "") or "").strip()
            akt_val = str(kontering_src.get("akt", "") or "").strip()
            projakt_val = str(kontering_src.get("projakt", "") or "").strip()
            projkat_val = str(kontering_src.get("projkat", "") or "").strip()

            # Bestäm typ av kontering
            if konproj_val and rg_val:
                warnings.append(
                    f"Konteringsregel har både konproj och rg satta (konproj={konproj_val}, rg={rg_val}). "
                    "Behandlar som projektkontering."
                )
                rg_out = ""
                konproj_out = konproj_val
                projkat_out = projkat_val
            elif konproj_val:
                rg_out = ""
                konproj_out = konproj_val
                projkat_out = projkat_val
            elif rg_val:
                rg_out = rg_val
                konproj_out = projkat_val
                projkat_out = ""
            else:
                # Fallback om varken rg eller konproj är satt: lägg kontot i Kon/Proj
                rg_out = ""
                konproj_out = projkat_val
                projkat_out = ""

            return {
                "Kon/Proj": konproj_out,
                "_empty1": "",
                "RG": rg_out,
                "Aktivitet": akt_val,
                "ProjAkt": projakt_val,
                "ProjKat": projkat_out,
                "_empty2": "",
                "Netto": belopp,
                "Godkänt av": godkant_av,
                "KommentarBeskrivning": kommentar or ""
            }

        for _, row in df.iterrows():
            resource_id = row.get("ResourceId", "")
            regel = self.hitta_konteringsregel(resource_id, resource_kontering_regler)
            if regel:
                kontering = build_kontering_row(
                    regel,
                    belopp=row.get("CostInBillingCurrency", 0),
                    kommentar=regel.get("beskrivning", ""),
                    godkant_av=config.get("godkant_av", "John Munthe"),
                )
                rows.append(kontering)
                continue
            # DevOps-logik
            if row.get('MeterCategory') == "Azure DevOps":
                devops = config.get("devops", {})
                mapping = devops.get("default", {})
                mappings = devops.get("mappings", [])
                subcat = row.get("MeterSubCategory", "")
                metername = row.get("MeterName", "")
                for m in mappings:
                    if m.get("subcat", "").strip().lower() == subcat.strip().lower() and m.get("metername", "").strip().lower() == metername.strip().lower():
                        mapping = m
                        break
                kommentar_beskrivning = mapping.get("beskrivning") or f"Avser Azure DevOps: {subcat} ({metername})"
                kontering = build_kontering_row(
                    mapping,
                    belopp=row.get("CostInBillingCurrency", 0),
                    kommentar=kommentar_beskrivning,
                    godkant_av=config.get("godkant_av", "John Munthe"),
                )
                rows.append(kontering)
                continue
            # Uppsamlingskontering
            upps = config.get("uppsamlingskontering", {})
            kommentar_beskrivning = upps.get("beskrivning") or row.get("BillingDescriptionTag", "") or "Ingen beskrivning angiven"
            kontering = build_kontering_row(
                upps,
                belopp=row.get("CostInBillingCurrency", 0),
                kommentar=kommentar_beskrivning,
                godkant_av=config.get("godkant_av", "John Munthe"),
            )
            rows.append(kontering)

        # Definiera kolumnordning med unika tomma kolumner
        kolumner = [
            "Kon/Proj", "_empty1", "RG", "Aktivitet", "ProjAkt", "ProjKat", "_empty2", "Netto", "Godkänt av", "KommentarBeskrivning"
        ]

        # Skapa DataFrame även om rows är tom
        kontering_df = pd.DataFrame(rows, columns=kolumner)

        # Gruppera och summera per relevant kombination om det finns rader
        if not kontering_df.empty:
            def group_key(row):
                if str(row["Kon/Proj"]).startswith("P."):
                    return (row["Kon/Proj"], row["Aktivitet"], row["ProjKat"], row["Godkänt av"])
                else:
                    return (row["RG"], row["Aktivitet"], row["Kon/Proj"], row["Godkänt av"])
            kontering_df["_group"] = kontering_df.apply(group_key, axis=1)
            grouped = kontering_df.groupby("_group", dropna=False).agg({
                "Kon/Proj": "first",
                "_empty1": "first",
                "RG": "first",
                "Aktivitet": "first",
                "ProjAkt": "first",
                "ProjKat": "first",
                "_empty2": "first",
                "Netto": "sum",
                "Godkänt av": "first",
                "KommentarBeskrivning": lambda x: x.iloc[0] if (x.nunique() == 1) else "Ingen beskrivning angiven"
            }).reset_index(drop=True)
            kontering_df = grouped
            # Filtrera bort rader där Netto = 0
            kontering_df = kontering_df[kontering_df["Netto"] != 0]
        # Summeringsrad
        total = kontering_df["Netto"].sum() if not kontering_df.empty else 0
        sumrad = {col: "" for col in kontering_df.columns}
        sumrad["Netto"] = total
        sumrad["Kon/Proj"] = "SUMMA"
        kontering_df = pd.concat([kontering_df, pd.DataFrame([sumrad])], ignore_index=True)
        return kontering_df, warnings

    def export_to_excel(self, df, filename=None):
        """
        Exporterar data till en Excel-fil med tre flikar:
        - Kontering (med periodinfo överst och konteringstabell)
        - Pivot (instruktion för pivottabell)
        - Data (hela DataFrame som Excel-tabell med filter och valutaformat)
        """
        import pandas as pd
        from datetime import datetime

        # Hämta period från BillingPeriodStartDate och BillingPeriodEndDate
        if 'BillingPeriodStartDate' in df.columns and 'BillingPeriodEndDate' in df.columns:
            start = pd.to_datetime(df['BillingPeriodStartDate'].min()).strftime('%Y-%m-%d')
            end = pd.to_datetime(df['BillingPeriodEndDate'].max()).strftime('%Y-%m-%d')
            period_str = f"Denna rapport gäller perioden: {start} till {end}"
            # För filnamn: YYYY-MM
            period_suffix = pd.to_datetime(df['BillingPeriodStartDate'].min()).strftime('%Y-%m')
        else:
            period_str = "Period okänd (BillingPeriodStartDate/BillingPeriodEndDate saknas)"
            period_suffix = datetime.now().strftime('%Y-%m')

        # Sätt filnamn om det inte är angivet
        if not filename:
            filename = f"reports/azure_cost_report_export_{period_suffix}.xlsx"

        # Läs in konteringskonfiguration från fil
        kontering_config = self.load_kontering_config()

        # Skapa konteringstabell
        kontering_df, warnings = self.generate_konteringsrader(df, kontering_config)
        if warnings:
            for w in warnings:
                self.logger.warning(w)

        with pd.ExcelWriter(filename, engine='xlsxwriter') as writer:
            # Flik 1: Kontering (med periodinfo överst och konteringstabell)
            workbook  = writer.book
            worksheet_konter = workbook.add_worksheet('Kontering')
            writer.sheets['Kontering'] = worksheet_konter
            worksheet_konter.write(0, 0, period_str)
            # Skriv ut konteringstabellen med start på rad 2 (index=1)
            # Skriv rubriker, men tomma för _empty1 och _empty2, och exkludera KommentarBeskrivning
            headers = ["Kon/Proj", "", "RG", "Aktivitet", "ProjAkt", "ProjKat", "", "Netto", "Godkänt av"]
            for col_idx, col in enumerate(headers):
                worksheet_konter.write(1, col_idx, col)
            # Skriv endast ut dessa kolumner från kontering_df
            export_cols = ["Kon/Proj", "_empty1", "RG", "Aktivitet", "ProjAkt", "ProjKat", "_empty2", "Netto", "Godkänt av"]
            for row_idx, row in enumerate(kontering_df[export_cols].itertuples(index=False), start=2):
                for col_idx, value in enumerate(row):
                    worksheet_konter.write(row_idx, col_idx, value)

            # Flik 2: Pivot (instruktion)
            worksheet_pivot = workbook.add_worksheet('Pivot')
            writer.sheets['Pivot'] = worksheet_pivot
            # Skapa format för instruktionstexten
            wrap_format = workbook.add_format({
                'text_wrap': True,
                'valign': 'top',
                'align': 'left'
            })
            instruktion = (
                "Skapa en pivottabell så här:\n"
                "1. Markera cellen B4 i fliken Pivot\n"
                "2. Välj Infoga > Pivottabell > Från tabell/intervall.\n"
                "3. Skriv Data i fältet för Tabell/område.\n"
                "4. Låt värdet Pivot!$B$4 stå kvar i fältet för Plats.\n"
                "5. Dra t.ex. CostCenterTag till Rader och CostInBillingCurrency till Värden.\n"
                "Du kan sedan utforska datat fritt!"
            )
            worksheet_pivot.write(0, 0, instruktion, wrap_format)
            worksheet_pivot.set_column(0, 0, 60)  # Sätt kolumnbredd till 60 tecken
            worksheet_pivot.set_row(0, 120)  # Sätt radhöjd till 120 pixlar

            # Flik 3: Data (hela DataFrame som tabell)
            df.to_excel(writer, sheet_name='Data', index=False, header=True, startrow=0)
            worksheet_data = writer.sheets['Data']
            (max_row, max_col) = df.shape

            def excel_col(n):
                s = ''
                while n >= 0:
                    s = chr(n % 26 + ord('A')) + s
                    n = n // 26 - 1
                return s

            last_col = excel_col(max_col - 1)
            table_range = f"A1:{last_col}{max_row+1}"

            currency_format = workbook.add_format({'num_format': '#,##0.00 "kr"'})
            if 'CostInBillingCurrency' in df.columns:
                col_idx = df.columns.get_loc('CostInBillingCurrency')
                col_letter = excel_col(col_idx)
                worksheet_data.set_column(f'{col_letter}:{col_letter}', None, currency_format)

            worksheet_data.add_table(table_range, {
                'name': 'Data',
                'columns': [{'header': col} for col in df.columns],
                'autofilter': True
            })

        self.logger.info(f"Excel-fil skapad: {filename}")

        # Efter att kontering_df och warnings skapats i export_to_excel:
        # ...
        # Generera kommentarer för inklistring i Medius
        print("\nKommentarer för inklistring i Medius:")
        # Hämta periodinfo
        period = period_str.replace("Denna rapport gäller perioden: ", "")
        # Skriv ut kommentarerna numrerat direkt från kontering_df (utom summeringsraden)
        for idx, row in enumerate(kontering_df.iloc[:-1].itertuples(index=False), 1):
            kommentar = getattr(row, "KommentarBeskrivning", "")
            # Om kommentaren är "Ingen beskrivning angiven", försök hitta unika BillingDescriptionTag i matchande rader
            if kommentar == "Ingen beskrivning angiven":
                row_dict = row._asdict()
                kon_proj = row_dict.get("Kon/Proj")
                aktivitet = row_dict.get("Aktivitet")
                projkat = row_dict.get("ProjKat")
                godkant_av = row_dict.get("Godkänt av")
                rg = row_dict.get("RG")
                # Hitta matchande rader i df för denna konteringsrad
                if str(kon_proj).startswith("P."):
                    group = (kon_proj, aktivitet, projkat, godkant_av)
                elif rg:
                    group = (rg, aktivitet, kon_proj, godkant_av)
                else:
                    group = (rg, aktivitet, projkat, godkant_av)
                # Hämta matchande rader ur df (ursprungsdata)
                match_rows = df.copy()
                match_rows["_group"] = match_rows.apply(lambda r: (f"P.{r['BillingProjTag']}" if str(r.get("BillingProjTag", "")).startswith("P.") or str(r.get("BillingProjTag", "")).isdigit() else r.get("BillingRGTag", ""), r.get("BillingAktTag", ""), r.get("BillingKatTag", ""), kontering_config.get("godkant_av", "John Munthe")), axis=1)
                match_rows = match_rows[match_rows["_group"] == group]
                descs = match_rows["BillingDescriptionTag"].dropna().unique()
                descs = [d for d in descs if d and str(d).strip() != ""]
                if len(descs) == 1:
                    kommentar = f"Avser: {descs[0]}"
                elif len(descs) > 1:
                    kommentar = f"Flera beskrivningar: {', '.join(descs)}"
                else:
                    kommentar = f"Ingen beskrivning angiven"
            # Lägg bara till perioden om den inte redan finns i kommentaren
            if "period:" not in kommentar:
                kommentar = f"{kommentar}, period: {period}"
            print(f"{idx}. {kommentar}")

    def process_cost_data(self, report_url=None, local_file_path=None):
        """
        Bearbetar kostnadsdata från den detaljerade rapporten.
        Args:
            report_url (str, optional): URL till den genererade rapporten
            local_file_path (str, optional): Sökväg till en befintlig rapportfil
        Returns:
            pd.DataFrame: Bearbetad data i konteringsformat
        """
        try:
            self.logger.info("Bearbetar kostnadsdata från detaljerad rapport")
            
            if report_url:
                # Skapa reports-mappen om den inte finns
                reports_dir = "reports"
                os.makedirs(reports_dir, exist_ok=True)
                
                # Generera filnamn baserat på datum
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                local_filename = os.path.join(reports_dir, f"azure_cost_report_{timestamp}.csv.gz")
                
                # Ladda ner filen
                self.logger.info(f"Laddar ner rapport till {local_filename}")
                with requests.get(report_url, stream=True) as r:
                    r.raise_for_status()
                    with open(local_filename, 'wb') as f:
                        for chunk in r.iter_content(chunk_size=8192):
                            f.write(chunk)
                self.logger.info(f"Rapport nedladdad framgångsrikt till {local_filename}")
                
                file_to_process = local_filename
            elif local_file_path:
                file_to_process = local_file_path
            else:
                raise ValueError("Antingen report_url eller local_file_path måste anges")

            # Kontrollera om filen är gzip-komprimerad genom att läsa de första bytena
            with open(file_to_process, 'rb') as f:
                magic = f.read(2)
            
            # Läs in CSV-filen med rätt inställningar
            self.logger.info(f"Läser in CSV-data från {file_to_process}")
            if magic == b'\x1f\x8b':  # gzip magic number
                self.logger.info("Filen är gzip-komprimerad")
                df = pd.read_csv(file_to_process, compression='gzip')
            else:
                self.logger.info("Filen är en vanlig CSV-fil")
                # Öppna filen explicit i textläge med UTF-8 encoding
                with open(file_to_process, 'r', encoding='utf-8-sig') as f:
                    df = pd.read_csv(f)
            
            self.logger.info(f"CSV-data inläst framgångsrikt. Antal rader: {len(df)}")
            
            # Skriv ut kolumnnamnen för att se vad vi har att arbeta med
            # logger.info("Tillgängliga kolumner i rapporten:")
            # for col in df.columns:
            #     logger.info(f"- {col}")

            # Summera hela kolumnen CostInBillingCurrency
            if 'CostInBillingCurrency' in df.columns:
                total_cost = df['CostInBillingCurrency'].sum()
                self.logger.info(f"\nTOTALSUMMA för CostInBillingCurrency: {total_cost:,.2f}\n")
            else:
                self.logger.warning("Kolumnen 'CostInBillingCurrency' saknas i rapporten!")

            # Subtotaler per ResourceGroup, MeterCategory och SubscriptionName
            for group_col in ['ResourceGroup', 'MeterCategory', 'SubscriptionName']:
                if group_col in df.columns:
                    self.logger.info(f"\nSUBTOTALER per {group_col}:")
                    subtotals = df.groupby(group_col)['CostInBillingCurrency'].sum().sort_values(ascending=False)
                    for name, subtotal in subtotals.items():
                        self.logger.info(f"  {name}: {subtotal:,.2f}")
                else:
                    self.logger.warning(f"Kolumnen '{group_col}' saknas i rapporten!")

            # Extrahera costcenter-taggen ur Tags-kolumnen
            if 'Tags' in df.columns:
                self.logger.info("\nExtraherar taggar ur Tags-kolumnen...")
                # Använd apply med extract_tags för att extrahera alla taggar
                df = df.apply(lambda row: self.extract_tags(row), axis=1)
            else:
                self.logger.warning("Kolumnen 'Tags' saknas i rapporten!")

            # Efter bearbetning: exportera till Excel
            self.export_to_excel(df)

            # Här kommer vi senare att lägga till kod för att bearbeta datan
            # För nu returnerar vi bara DataFrame
            return df
        
        except Exception as e:
            self.logger.error(f"Fel vid bearbetning av kostnadsdata: {str(e)}")
            raise

def main():
    try:
        # Lägg till argumenthantering
        parser = argparse.ArgumentParser(description='Azure Cost Processor')
        parser.add_argument('-v', '--verbose', action='store_true', help='Aktivera detaljerad loggning')
        args = parser.parse_args()
        
        # Konfigurera loggning baserat på verbose-flaggan
        logger = setup_logging(args.verbose)
        
        processor = AzureCostProcessor(logger)
        logger.info("Azure Cost Processor startad")
        
        # Fråga användaren om de vill generera en ny rapport eller bearbeta en befintlig
        print("\nVälj alternativ:")
        print("1. Generera ny kostnadsrapport från Azure")
        print("2. Bearbeta befintlig rapportfil")
        choice = input("Ange ditt val (1 eller 2): ").strip()
        
        if choice == "1":
            # Fråga om användaren vill ange en period
            period = input("Ange rapportperiod (YYYYMM) eller lämna tomt för standard: ").strip()
            if period:
                try:
                    period_date = datetime.strptime(period, "%Y%m")
                    today = datetime.today()
                    # Om perioden är mer än 11 månader bakåt i tiden
                    if (today.year - period_date.year) * 12 + (today.month - period_date.month) > 11:
                        confirm = input(f"Du har valt perioden {period_date.strftime('%Y-%m')}, vilket är mer än 11 månader bakåt i tiden. Är du säker på att du vill fortsätta? (j/n): ").strip().lower()
                        if confirm != 'j':
                            print("Avbryter på begäran av användaren.")
                            return
                except Exception:
                    print("Felaktigt format på period. Ange som 'YYYYMM'.")
                    return
            if not config.AZURE_BILLING_ACCOUNT_ID:
                raise ValueError("AZURE_BILLING_ACCOUNT_ID måste anges i .env-filen")
            report_url = processor.generate_detailed_cost_report_billing_account(config.AZURE_BILLING_ACCOUNT_ID, period if period else None)
            if report_url:
                processed_data = processor.process_cost_data(report_url)
                logger.info("Kostnadsdata bearbetad framgångsrikt")
        
        elif choice == "2":
            # Bearbeta befintlig fil
            print("\nTillgängliga rapporter i 'reports'-mappen:")
            reports_dir = "reports"
            if os.path.exists(reports_dir):
                files = [f for f in os.listdir(reports_dir) if f.endswith('.csv.gz')]
                if not files:
                    print("Inga rapporter hittades i 'reports'-mappen.")
                    return
                
                for i, file in enumerate(files, 1):
                    print(f"{i}. {file}")
                
                file_choice = input("\nVälj rapport att bearbeta (ange nummer): ").strip()
                try:
                    selected_file = files[int(file_choice) - 1]
                    file_path = os.path.join(reports_dir, selected_file)
                    logger.info(f"Bearbetar befintlig rapport: {selected_file}")
                    processed_data = processor.process_cost_data(None, file_path)
                    logger.info("Kostnadsdata bearbetad framgångsrikt")
                except (ValueError, IndexError):
                    print("Ogiltigt val. Avslutar.")
                    return
            else:
                print("'reports'-mappen hittades inte.")
                return
        else:
            print("Ogiltigt val. Avslutar.")
            return
        
    except Exception as e:
        logger.error(f"Ett fel uppstod: {str(e)}")
        raise

if __name__ == "__main__":
    main() 