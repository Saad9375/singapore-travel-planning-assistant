# Sample Questions and Application Responses

These illustrate the expected behaviour of each feature. Actual wording will vary slightly by LLM
run; run the app with a valid `GOOGLE_API_KEY` to reproduce live.

Every answer separates three channels: `[Knowledge Base]` for retrieved destination facts,
`[MCP Tool]` for live tool results, and `[Recommendation]` for the model's own synthesis.
`[Recommendation]` appears only when the user actually asked for advice or planning -- a plain
lookup is answered and closed.

## 1. RAG only (destination knowledge)

**Q: What are the must-visit attractions in Singapore?**

> [Knowledge Base] (Wikivoyage: Singapore District Guides)
> - **Marina Bay** -- Marina Bay Sands, Gardens by the Bay with the Supertree Grove and the Cloud
>   Forest and Flower Dome conservatories, and the Merlion.
> - **Chinatown** -- restored shophouses, the Buddha Tooth Relic Temple and the Sri Mariamman
>   Temple, and the Chinatown Complex Food Centre.
> - **Little India** -- the Sri Veeramakaliamman Temple and the Tekka Centre wet market.
> - **Sentosa** -- beaches, S.E.A. Aquarium and Universal Studios Singapore.
>
> 📚 Sources: Wikivoyage: Singapore District Guides

## 2. MCP only (weather)

**Q: What is the forecast for the next three days?**

> [MCP Tool] (get_weather_forecast, Open-Meteo API)
> - 2026-09-20: Max 31.1°C, Min 26.2°C, rain probability 99%
> - 2026-09-21: Max 31.0°C, Min 26.2°C, rain probability 92%
> - 2026-09-22: Max 31.8°C, Min 26.2°C, rain probability 95%
>
> 🔧 Tool used: get_weather_forecast(destination="Singapore", days=3)

## 3. MCP only (currency)

**Q: Convert INR 50,000 to SGD.**

> [MCP Tool] (convert_currency, Frankfurter API)
> INR 50,000 converts to approximately SGD 667 at the current reference rate.
>
> 🔧 Tool used: convert_currency(amount=50000, from_currency="INR", to_currency="SGD")

Note the absence of a `[Recommendation]` section -- a plain lookup gets an answer and nothing else.

## 4. Combined RAG + MCP (required scenario)

**Q: Create a three-day Singapore itinerary for next week and adjust it according to the weather forecast.**

> [Knowledge Base] (Wikivoyage: Three Days in Singapore)
> - **Day 1 (The Tourist Loop):** the typical touristy face of Singapore. Approx. $50 per person for
>   admissions and transport.
> - **Day 2 (Culture Vulture):** loops through Chinatown and Little India, taking the North-East
>   Line MRT between them and visiting the Tekka Centre. Approx. $10 per person.
> - **Beach Bumming:** Sentosa, with food and drink stocked up more cheaply at the VivoCity or
>   HarbourFront supermarkets first.
> - Practical note: tropical heat with afternoon thunderstorms; bring an umbrella and water, start
>   early, and duck into air-conditioned shops and museums to take shelter.
>
> [MCP Tool] (get_weather_forecast, Open-Meteo API)
> - 2026-09-20: rain probability 99% | 2026-09-21: 92% | 2026-09-22: 95%
>
> [Recommendation]
> - With a 92-99% rain probability across all three days, start each day early, carry an umbrella,
>   and schedule indoor activities around midday.
> - **Day 1 (Tourist Loop):** keep the classic sights to the morning, with an umbrella ready.
> - **Day 2 (Culture Vulture):** time the Tekka Centre indoor market stroll for midday so you are
>   sheltered if the afternoon thunderstorms arrive.
> - **Day 3 (Sentosa):** a strict beach day risks being washed out at 95% rain -- stock up at the
>   VivoCity supermarkets first and be ready to pivot to indoor attractions.
>
> 📚 Sources: Wikivoyage: Three Days in Singapore, Wikivoyage: Singapore Practical Travel Information
> 🔧 Tool used: get_weather_forecast(destination="Singapore", days=3)

Note that the day-by-day weather adjustment sits under `[Recommendation]`, not `[MCP Tool]` -- the
forecast came from the tool, but deciding what to do about it is the model's own synthesis.

## 5. Combined RAG + MCP (budget scenario)

**Q: I have a budget of INR 60,000. Convert it to SGD and suggest a three-day itinerary.**

> [MCP Tool] (convert_currency, Frankfurter API)
> INR 60,000 converts to approximately SGD 800 at the current reference rate.
>
> [Knowledge Base] (Wikivoyage: Three Days in Singapore, Wikivoyage: Singapore Food & Local Experiences)
> - The three-day itinerary estimates roughly $50 per person for the Tourist Loop day and $10 for
>   the Culture Vulture day, excluding food and hotel transfers.
> - Hawker-centre dishes run about $3-5; the same dish is $5-10 in a food court.
>
> [Recommendation]
> - The admissions and transport in the knowledge base itinerary come to well under your budget,
>   which leaves the bulk of it for food and accommodation.
> - Eating at hawker centres rather than food courts roughly halves the per-meal cost.
>
> 📚 Sources: Wikivoyage: Three Days in Singapore, Wikivoyage: Singapore Food & Local Experiences
> 🔧 Tool used: convert_currency(amount=60000, from_currency="INR", to_currency="SGD")

## 6. Missing knowledge base info (graceful failure)

**Q: What's the best nightclub in Singapore for techno music?**

> [Knowledge Base] The knowledge base doesn't cover nightlife or specific music venues, so I can't
> answer that from verified sources.

## 7. Tool failure handling

**Q: What is the weather in Singapore?** (simulated network failure)

> [MCP Tool] The weather tool is currently unavailable (network error), so I can't provide a live
> forecast right now. I won't guess at conditions.

## 8. Multi-turn context

**Turn 1 -- Q: I'm travelling with two young kids and a budget of SGD 500 for activities.**
> Noted -- I'll keep that in mind for the rest of this conversation.

**Turn 2 -- Q: Suggest a 2-day itinerary.**
> [Knowledge Base] (Wikivoyage: Singapore District Guides, Wikivoyage: Three Days in Singapore)
> Sentosa has the S.E.A. Aquarium and beaches; Marina Bay has the Cloud Forest and Flower Dome
> conservatories, which are indoor and air-conditioned...
>
> [Recommendation]
> Given you're travelling with young kids (from earlier), the air-conditioned conservatories and the
> aquarium are the gentler options in the tropical heat, and both fall inside your stated budget...
