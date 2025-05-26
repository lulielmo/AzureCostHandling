# Konteringsregler för Azurekostnad → Medius

## Bakgrund
- Azurekostnader faktureras via Atea utan detaljerad resursinformation.
- Vi laddar ner detaljerad kostnadsrapport från Azure och skapar konteringsrader för Medius.
- Taggningen i Azure är under uppbyggnad och kan saknas eller vara ofullständig.

## Taggning i Azure

### Viktigt att veta
- Taggar ärvs **inte** mellan nivåer i Azure (t.ex. från resursgrupp till resurser)
- För att få korrekta konteringsrader måste taggarna sättas på **resursnivå**
- Om en resursgrupp har taggar men resurserna i gruppen inte har det, kommer kostnaderna för resurserna inte att inkluderas i konteringsrapporten

### Hur man taggar
1. **För resursgrupper:**
   - Sätt taggarna direkt på resursgruppen för att dokumentera avsikten
   - Men kom ihåg att detta inte påverkar konteringsrapporten

2. **För resurser:**
   - Sätt följande taggar på **varje resurs** som ska konteras:
     - `Billing-RG` (om resursen ska konteras på resursgruppsnivå)
     - `Billing-proj` (om resursen ska konteras på projektnivå)
     - `Billing-kat` (för konteringskategori)
     - `Billing-akt` (för aktivitetskod)
   - Detta kan göras manuellt i Azure Portal eller via Azure CLI/PowerShell

3. **Bästa praxis:**
   - Använd Azure Policy för att automatiskt tillämpa taggar på nya resurser
   - Skapa en rutin för att regelbundet kontrollera att alla resurser har rätt taggar
   - Dokumentera taggningskonventioner i teamets wiki eller liknande

## Styr konteringen med konfigurationsfil

För att förenkla och centralisera konteringsreglerna används nu en konfigurationsfil (t.ex. `kontering_resource_config.json`) där du pekar ut vilka resurser som ska konteras på vilket sätt. Detta gör att du slipper tagga varje resurs i Azure och istället styr allt från ett ställe.

### Så fungerar det
- Du anger en eller flera regler i filen.
- Varje regel innehåller en lista av `resource_ids` (wildcard eller exakta ResourceId:n) och de konteringsvärden som ska användas.
- Första matchande regel gäller för en resurs.
- DevOps och uppsamlingskontering fungerar som tidigare.

### Exempel på konfigurationspost
```json
{
  "resource_ids": [
    "*/resourceGroups/D365-TESTUPDATE/*",
    "*/resourceGroups/DynamicsDeployments-westeurope/*"
  ],
  "konproj": "P.20210002",
  "rg": "",
  "akt": "D365",
  "projkat": "5420",
  "beskrivning": "Samtliga D365-relaterade resurser oavsett subscription"
}
```

### Principer
- Du kan använda wildcard (`*`) för att matcha hela subscriptions, resursgrupper eller enskilda resurser.
- Du kan ha flera regler och kombinera olika nivåer av precision.
- Om ingen regel matchar används uppsamlingskonteringen.

### Så här gör du
1. Skapa eller uppdatera filen `kontering_resource_config.json` enligt exemplen ovan.
2. Lägg till, ta bort eller ändra regler efter behov.
3. När du kör skriptet kommer det att använda dessa regler för att styra konteringen.

Kontakta systemansvarig om du vill ha hjälp att lägga till nya regler eller om du är osäker på hur du ska formulera ett wildcard.

## Taggar och konteringslogik

### Taggar som används:
- **Billing-RG**
- **Billing-proj**
- **Billing-kat**
- **Billing-akt**

### Regler för konteringsrader:
- **Endast en av Billing-RG eller Billing-proj ska vara satt per rad.**
    - Om båda är satta: logga varning, men behandla raden som Billing-proj.
- **Om Billing-RG är satt:**
    - RG = Billing-RG
    - Kon/Proj = Billing-kat
    - Aktivitet = Billing-akt
    - ProjKat lämnas tom
- **Om Billing-proj är satt:**
    - Kon/Proj = P.{Billing-proj}
    - ProjKat = Billing-kat
    - Aktivitet = Billing-akt
    - RG lämnas tom

### Specialfall:
- **Azure DevOps-kostnader** (MeterCategory = "Azure DevOps"):
    - Kan inte taggas, grupperas på MeterSubCategory.
    - Konteras på särskild (konfigurerbar) kontering.
- **Rader utan Billing-RG eller Billing-proj:**
    - Läggs på en uppsamlingskontering (konfigurerbar).
    - Allteftersom taggningen förbättras minskar denna post.

## Excel-kolumner för Medius
- **Kon/Proj**
- **RG**
- **Aktivitet**
- **ProjKat**
- **Netto** (summerad kostnad för raden, utan tusentalsavgränsare)
- **Godkänt av** (från konfigurationsfil, default: John Munthe, ev. från inloggad användare)
- (Eventuellt fler kolumner om Medius kräver)

## Övrigt
- Summeringsrad i slutet för att validera att konteringen täcker hela fakturabeloppet.
- All logik och konteringsregler ska vara dokumenterade och konfigurerbara där det är möjligt.

## Tidsstyrda tagg-override (avancerat)

I vissa fall kan det vara nödvändigt att ändra konteringsregler retroaktivt eller från ett visst datum, t.ex. om en tagg varit felaktig under en period. Detta kan göras med hjälp av filen `tag_overrides.json`.

Exempel på innehåll:

```json
{
  "overrides": [
    {
      "resource_id": "*/resourceGroups/mygroup/*",
      "tag": "Billing-akt",
      "value": "006",
      "valid_from": "2024-01-01",
      "valid_to": "2024-05-15"
    },
    {
      "resource_id": "*/resourceGroups/mygroup/*",
      "tag": "Billing-akt",
      "value": "050",
      "valid_from": "2024-05-16",
      "valid_to": null
    }
  ]
}
```

- `resource_id` kan vara ett mönster (wildcard) som matchar ResourceId i rapporten.
- `tag` är namnet på taggen som ska skrivas över.
- `value` är det värde som ska användas under perioden.
- `valid_from` och `valid_to` anger under vilken period override gäller (format: YYYY-MM-DD).

Om en override finns för en resurs, tagg och datum används override-värdet istället för det som står i rapporten. Annars används taggen från rapporten som vanligt. 