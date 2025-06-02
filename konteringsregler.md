# Konteringsregler för Azurekostnad → Medius

## Bakgrund
- Azurekostnader faktureras via Atea utan detaljerad resursinformation.
- Vi laddar ner detaljerad kostnadsrapport från Azure och skapar konteringsrader för Medius.

## Ordlista: Fält i konteringskonfigurationen

- **konproj**: Projektkod (t.ex. "P.98116002"). Används om konteringen ska läggas mot en projekt.
- **rg**: Rörelsegren (t.ex. 74000), används om konteringen ska läggas mot en rörelsegren.
- **akt**: Aktivitetskod (t.ex. "738", "999", "050").
- **projkat**: Konto (t.ex. "6540", "5910"). Läggs i fältet ProjKat om kontering sker mot projekt eller i fältet KonProj om kontering sker mot rörelsegren.
- **beskrivning**: Fri text som beskriver vad raden avser (används som kommentar i Medius).

Dessa fält anges i regler i filerna `kontering_resource_config.json` (för vanliga resurser) och `kontering_config.json` (för DevOps och uppsamlingskontering).

## Konteringslogik

Konteringsrader skapas genom att varje rad i kostnadsrapporten matchas mot regler i konfigurationsfilerna:

1. **kontering_resource_config.json**: Här anges regler med `resource_ids` (wildcards eller exakta sökvägar). Första matchande regel styr konteringen för raden och anger värden för konproj, rg, akt, projkat och beskrivning.
2. **kontering_config.json**:
   - Om raden gäller Azure DevOps (MeterCategory = "Azure DevOps") används DevOps-reglerna.
   - Om ingen regel matchar används uppsamlingskonteringen.

Varje konteringsrad får sina värden direkt från dessa regler. Ingen taggning i Azure krävs längre för konteringssyfte.

### Exempel på konteringsrader (en projektkontering och en rörelsegrenskontering):
> **OBS!** De tomma kolumnerna (markerade med |) är avsiktliga och behövs för att Excel-filen ska kunna importeras korrekt i Medius.

| Kon/Proj   | | RG    | Aktivitet | ProjKat | | Netto    | Godkänt av   |
|------------|-|-------|-----------|---------|-|----------|--------------|
| P.98116002 | |       | 006       | 6540    | | 9133,89  | John Munthe  |
| 6540       | | 14000 | 999       |         | | 5764,76  | John Munthe  |

Se övriga sektioner för exempel på hur du bygger regler och grupperar resurser.

## Viktigt: All konteringsstyrning sker nu via konfigurationsfil

> **OBS!** Du behöver inte längre tagga resurser i Azure för konteringssyfte. All gruppering och kontering styrs nu via mönster (wildcards) på ResourceId i filen `kontering_resource_config.json`.

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

#### Fler exempel på gruppering med resourceId-mönster
- **Alla resurser i en subscription:**
  ```json
  "resource_ids": ["*/subscriptions/<subscription-id>/*"]
  ```
- **Alla resurser i en eller flera resursgrupper:**
  ```json
  "resource_ids": ["*/resourceGroups/rg1/*", "*/resourceGroups/rg2/*"]
  ```
- **Enskilda resurser:**
  ```json
  "resource_ids": ["*/resourceGroups/rg1/providers/microsoft.web/sites/minapp"]
  ```

Kontakta systemansvarig om du vill ha hjälp att lägga till nya regler eller om du är osäker på hur du ska formulera ett wildcard.

## Konfigurationsvärden och konteringslogik

### Värden som används:
- **rg**
- **konproj**
- **projkat**
- **akt**

### Regler för konteringsrader:
- **Endast en av rg eller konproj ska vara satt per rad.**
    - Om båda är satta: logga varning, men behandla raden som projektkontering.
- **Om rg är satt (rörelsegrenskontering):**
    - RG = rg
    - Kon/Proj = projkat
    - Aktivitet = akt
    - ProjKat lämnas tom
- **Om Billing-proj är satt (projektkontering):**
    - Kon/Proj = P.{konproj}
    - ProjKat = projkat
    - Aktivitet = akt
    - RG lämnas tom

### Specialfall:
- **Azure DevOps-kostnader** (MeterCategory = "Azure DevOps"):
    - Kan inte grupperas på resurs-id, grupperas på MeterSubCategory.
    - Konteras på särskild (konfigurerbar) kontering.
- **Rader som saknar konfiguration som pekar ut rg eller konproj:**
    - Läggs på en uppsamlingskontering (konfigurerbar).
    - Allteftersom konfigurationen förbättras minskar denna post.

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