# TODO

- [ ] Utvärdera om rollen **Cost Management Reader** behöver vara kvar på service principalen.
    - Om vi i framtiden vill köra rapporter direkt mot en eller flera subscriptions kan rollen behövas.
    - Om vi endast ska köra rapporter på billing account-nivå (EA) räcker det med **EnrollmentReader** och rollen kan tas bort för ökad säkerhet.

- [ ] Notera: Vi har implementerat en workaround för att hämta downloadUrl från operationResult-API eftersom Azure SDK för Python inte returnerar denna direkt vid rapportgenerering. Om SDK:n uppdateras i framtiden kan denna workaround behöva justeras eller tas bort. 