"""Item di lista e dettagli HofJ di esempio, come li restituisce `/v1/products` (M1, M10)."""


def item(pid, archived=False, **over):
    """Item della lista /v1/products come lo restituisce l'API (campi principali)."""
    base = {
        "id": str(pid), "slug": "padel-%d" % pid, "title": "Padel %d" % pid,
        "shortDescription": "breve", "description": "**lunga**", "archived": archived,
        "channelId": "1", "venueId": "194", "categoryId": "1", "destinationId": "17",
        "createdAt": "2026-03-09T09:26:05.776Z", "updatedAt": "2026-09-25T09:20:18.757Z",
        "publishedAt": "2026-03-10T11:54:04.217Z", "tripCode": "MKT_%d" % pid,
        "providerID": "t%07d" % pid, "price": 340, "currency": "EUR", "minPax": 2,
        "maxPax": None, "minDate": "2026-09-25", "maxDate": "2027-01-07",
        "defaultDurationInDays": 3, "hotelSelection": False, "locale": "it",
        "featured": False, "isSpecialOffer": False, "maxPaxPerRoom": None,
        "availabilities": [] if archived else [
            {"status": "Bookable", "startDate": "2026-09-28", "endDate": "2026-10-01",
             "serviceLevels": []}],
    }
    base.update(over)
    return base


def detail_of(list_item):
    """Dettaglio extended=true dello stesso prodotto, con i campi pesanti da scartare."""
    detail = dict(list_item)
    detail.update({
        "category": {"id": "1", "name": "Padel", "slug": "padel"},
        "venue": {"id": "194", "title": "Club", "slug": "club", "coverUrl": "https://x/v.jpg"},
        "destination": {"id": "17", "title": "Sinalunga", "slug": "sinalunga", "country": "IT",
                        "geohierarchy": "IT_123", "coverUrl": "https://x/d.jpg"},
        "image": {"url": "https://x/i.jpg", "width": 1, "height": 1},
        "gallery": [{"url": "https://x/g1.jpg", "source": "venue"}],
        "travelProgram": {"id": "733", "description": "...", "details": []},
        "rawAttributes": {
            "hotels": {"data": [{"id": 5, "attributes": {"name": "Hotel Uno",
                                                         "gallery": {"data": []}}}]},
            "gallery": {"data": [{"id": 1}]}, "cover": {"data": {"id": 2}},
            "playtomicLevel": "3",
        },
    })
    return detail
