# Konteringsregler för Azurekostnad → Medius

## Bakgrund
- Azurekostnader faktureras via Atea utan detaljerad resursinformation.
- Vi laddar ner detaljerad kostnadsrapport från Azure och skapar konteringsrader för Medius.
- Taggningen i Azure är under uppbyggnad och kan saknas eller vara ofullständig.

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