# Vela — buying a trip, three years from now

Twenty-four hours to design, build and deploy a working prototype on a live API. It is meant to be genuinely out of reach unless you delegate most of the work to AI agents — and we will be reading how you did that as closely as we read the result.



The premise

Today, buying a sports trip means opening six tabs, comparing prices that move when you refresh, guessing whether the hotel is near the courts, and booking out of exhaustion. AI is already dismantling that pattern, and we are only at the beginning of it.

**We are not asking you to build a better booking site.** We are asking you to build what replaces it.



### **In 2029 Vela has no homepage.**

Build how a traveller comes to own a padel or tennis trip when there is no site to visit.

**A submission that breaks any of these is not scored:**

- No search results page. No filter panel. No product grid. No comparison table.
- The traveller is never handed a list to choose from. If your system's answer to *"what should I book"* is *"here are twelve options"*, you have built the thing we asked you not to build.
- Assume the traveller's attention is not on a screen for most of the interaction.
- The entire purchase is reachable from a single expressed intent, in the traveller's own words.
- Vela is not a destination. The traveller does not come to you. You arrive where they already are.
- Not every buyer in 2029 has eyes, a screen, or patience.

We are not going to tell you what form this takes. Deciding that *is* the challenge, and the range of right answers is wider than you think. If your first instinct feels obvious, it probably is.



Scope

Padel or tennis experiences packaged with a hotel. That is the whole product. No flights, no transfers, no car hire, no other travel component — adding them will cost you marks rather than earn them.



The API you are building on

Everything you show a traveller must come from the **House of Journeys distribution API**. It is real, it is live, and the inventory in it is real. Documentation is at [docs.api.hofj.com](http://docs.api.hofj.com) and the full OpenAPI 3.1 document is public at [api.hofj.com/v1/openapi.json](https://api.hofj.com/v1/openapi.json).

### Things we will not explain twice

- There is a **rate limit**. It is a rolling window, it is smaller than you would like, and the API will not tell you politely when you hit it. `GET /v1/quota` exists. Budget accordingly, starting now.
- **Not every product is bookable.** Some of the catalogue is misconfigured upstream and will fail when you try to put it in a cart. Handle it. Real inventory is like this.
- Read the spec properly. Several things that look like they should work the obvious way do not, and finding that out at hour twenty is your own affair.

### Where you have to get to

A traveller expresses an intent, and ends up holding a real reservation code from a real booking against this API. Everything between those two points is your design. Payment runs through Stripe in test mode using the key above.



### Deliverables

- **A live URL.** Deploy wherever you like — we just have to be able to reach it and use it.
- **A public repository** with its full commit history intact.
- [`ARCHITECTURE.md`](http://ARCHITECTURE.md) — your decisions, your trade-offs, what you would do next.
- `/agent-log/` — raw agent transcripts.
- **A load test** we can run, plus the numbers you got.
- **A 3–5 minute video** of a real purchase completing, end to end.

### How we score it

- Working prototype that completes a real booking — **25%**
- Scalability architecture — **25%**
- Vision: did you escape the marketplace — **20%**
- Agentic method, evidenced — **15%**
- API mastery — **10%**
- Communication — **5%**

