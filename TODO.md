# TODO

- [ ] Då kontering sker på RG så ska kontot (t.ex. 5430) vara i kolumnen Kon/Proj och inte i ProjKat såsom den är nu. Kontot ska bara vara i ProjKat då det är projektkontering.

- [ ] Utvärdera om rollen **Cost Management Reader** behöver vara kvar på service principalen.
    - Om vi i framtiden vill köra rapporter direkt mot en eller flera subscriptions kan rollen behövas.
    - Om vi endast ska köra rapporter på billing account-nivå (EA) räcker det med **EnrollmentReader** och rollen kan tas bort för ökad säkerhet.

- [ ] Notera: Vi har implementerat en workaround för att hämta downloadUrl från operationResult-API eftersom Azure SDK för Python inte returnerar denna direkt vid rapportgenerering. Om SDK:n uppdateras i framtiden kan denna workaround behöva justeras eller tas bort. 

