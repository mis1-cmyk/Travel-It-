#!/usr/bin/env python3
"""
Travel Itinerary Generator v3.0 — "No Fake Places" Edition
==========================================================
Architecture (senior-level):
  1. Geocode destination (Nominatim + country detection)
  2. PRIMARY: Wikipedia GeoSearch — famous places only (have real articles)
  3. SECONDARY: Wikidata SPARQL — structured tourist attraction query
  4. SUPPLEMENT: OpenStreetMap Overpass — named tourism POIs (deduplicated)
  5. Enrich: batch Wikipedia image fetch (1 request for all places)
  6. Schedule: smart time slots (culture AM, outdoors PM, food/market evening)
  7. NO invented fallback names — honest generic suggestions only
All APIs are free, no keys required.
"""

import requests
import json
import sys
import time
import urllib.parse


class TravelItineraryGenerator:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'TravelItineraryBot/3.0 (Educational)'
        })
        self.wiki_api = "https://en.wikipedia.org/w/api.php"

    # ---------------------------------------------------------------
    # STEP 1: Geocoding (with country detection for context)
    # ---------------------------------------------------------------
    def geocode_location(self, location_name):
        try:
            params = {
                'q': location_name,
                'format': 'json',
                'limit': 1,
                'addressdetails': 1
            }
            r = self.session.get(
                "https://nominatim.openstreetmap.org/search",
                params=params, timeout=10
            )
            data = r.json()
            if not data:
                return None
            addr = data[0].get('address', {})
            return {
                'display_name': data[0]['display_name'],
                'lat': float(data[0]['lat']),
                'lon': float(data[0]['lon']),
                'city': addr.get('city') or addr.get('town') or addr.get('county', ''),
                'country': addr.get('country', '')
            }
        except Exception as e:
            print(f"Geocoding error: {e}")
            return None

    # ---------------------------------------------------------------
    # STEP 2 (PRIMARY): Wikipedia GeoSearch — famous places ONLY.
    # A place only appears here if it's notable enough for an article.
    # This is what kills "Harbor District"-style garbage suggestions.
    # ---------------------------------------------------------------
    def wiki_geosearch(self, lat, lon, radius=10000, limit=60):
        places = []
        try:
            params = {
                'action': 'query',
                'list': 'geosearch',
                'gscoord': f"{lat}|{lon}",
                'gsradius': radius,
                'gslimit': limit,
                'format': 'json'
            }
            r = self.session.get(self.wiki_api, params=params, timeout=10)
            for g in r.json().get('query', {}).get('geosearch', []):
                places.append({
                    'name': g['title'],
                    'pageid': g['pageid'],
                    'dist': g.get('dist', 0),
                    'source': 'wikipedia'
                })
            time.sleep(1)  # respect rate limits
        except Exception as e:
            print(f"  (Wikipedia geosearch note: {e})")
        return places

    # ---------------------------------------------------------------
    # STEP 3: Batch-enrich Wikipedia places with images + descriptions.
    # One single API call for all places — efficient, not N calls.
    # ---------------------------------------------------------------
    def enrich_from_wikipedia(self, places):
        if not places:
            return places
        try:
            pageids = '|'.join(str(p['pageid']) for p in places[:50])
            params = {
                'action': 'query',
                'pageids': pageids,
                'prop': 'pageimages|description',
                'pithumbsize': 500,
                'format': 'json'
            }
            r = self.session.get(self.wiki_api, params=params, timeout=10)
            pages = r.json().get('query', {}).get('pages', {})
            for pid, info in pages.items():
                for p in places:
                    if str(p['pageid']) == str(pid):
                        p['image'] = info.get('thumbnail', {}).get('source')
                        p['description'] = info.get('description', '').lower()
                        p['extract'] = info.get('extract', '')
            time.sleep(1)
        except Exception as e:
            print(f"  (Image enrichment note: {e})")
        return places

    # ---------------------------------------------------------------
    # STEP 4 (SECONDARY): Wikidata SPARQL — structured knowledge graph.
    # Finds attractions/castles/museums/temples geographically nearby.
    # ---------------------------------------------------------------
    def wikidata_attractions(self, lat, lon):
        places = []
        try:
            query = f"""
            SELECT DISTINCT ?item ?itemLabel ?coord WHERE {{
              ?item wdt:P31/wdt:P279*
                wd:Q570116 .               # tourist attraction (+ subclasses)
              ?item wdt:P625 ?coord .
              SERVICE wikibase:around {{
                ?item wdt:P625 ?coord .
                bd:serviceParam wikibase:center
                  "Point({lon} {lat})"^^geo:wktLiteral .
                bd:serviceParam wikibase:radius "8" .
              }}
              SERVICE wikibase:label {{
                bd:serviceParam wikibase:language "en" .
              }}
            }} LIMIT 40"""
            r = self.session.get(
                "https://query.wikidata.org/sparql",
                params={'query': query, 'format': 'json'},
                timeout=15
            )
            for b in r.json().get('results', {}).get('bindings', []):
                label = b['itemLabel']['value']
                # Skip Wikidata's own junk labels
                if not label or label.startswith('Q'):
                    continue
                places.append({
                    'name': label,
                    'pageid': None,
                    'dist': 0,
                    'source': 'wikidata',
                    'image': None,
                    'description': ''
                })
            time.sleep(1)
        except Exception as e:
            print(f"  (Wikidata note: {e})")
        return places

    # ---------------------------------------------------------------
    # STEP 5 (SUPPLEMENT): OpenStreetMap — real named POIs only.
    # Names like "Gateway of India" — never invented ones.
    # ---------------------------------------------------------------
    def osm_attractions(self, lat, lon):
        try:
            query = f"""
            [out:json][timeout:25];
            (
              node["tourism"~"attraction|museum|viewpoint|gallery|zoo"]
                (around:6000,{lat},{lon});
              node["historic"~"monument|castle|ruins|fort"]
                (around:6000,{lat},{lon});
              way["tourism"~"attraction"](around:6000,{lat},{lon});
            );
            out center 30;"""
            r = self.session.post(
                "https://overpass-api.de/api/interpreter",
                data={'data': query}, timeout=30
            )
            places = []
            for el in r.json().get('elements', []):
                tags = el.get('tags', {})
                name = tags.get('name')
                if not name or len(name) < 3:
                    continue  # skip unnamed/utility junk
                places.append({
                    'name': name,
                    'pageid': None,
                    'dist': 0,
                    'source': 'osm',
                    'image': None,
                    'description': tags.get('tourism', tags.get('historic', ''))
                })
            return places
        except Exception as e:
            print(f"  (OSM note: {e})")
            return []

    # ---------------------------------------------------------------
    # STEP 6: Merge all sources, dedupe, rank by fame.
    # Wikipedia places rank first (they're verified notable).
    # ---------------------------------------------------------------
    def collect_attractions(self, lat, lon):
        print("  📖 Searching Wikipedia for famous places...")
        wiki = self.enrich_from_wikipedia(self.wiki_geosearch(lat, lon))

        print("  🧠 Querying Wikidata knowledge graph...")
        wikidata = self.wikidata_attractions(lat, lon)

        print("  🗺️  Checking OpenStreetMap POIs...")
        osm = self.osm_attractions(lat, lon)

        merged, seen = [], set()
        for source_list in (wiki, wikidata, osm):  # priority order
            for p in source_list:
                key = p['name'].lower().strip()
                if key not in seen:
                    seen.add(key)
                    merged.append(p)

        print(f"  ✅ Found {len(merged)} unique real places")
        return merged

    # ---------------------------------------------------------------
    # STEP 7: Smart scheduling — match place type to time of day.
    # ---------------------------------------------------------------
    def categorize(self, place):
        text = f"{place.get('description','')} {place['name']}".lower()
        if any(k in text for k in ['museum', 'palace', 'castle', 'cathedral',
                                   'temple', 'mosque', 'church', 'fort',
                                   'monument', 'memorial', 'gallery']):
            return 'culture'       # morning
        if any(k in text for k in ['park', 'garden', 'beach', 'lake', 'hill',
                                   'zoo', 'sanctuary', 'viewpoint', 'island']):
            return 'outdoors'      # afternoon
        if any(k in text for k in ['market', 'bazaar', 'mall', 'street',
                                   'promenade', 'food', 'nightlife']):
            return 'evening'
        return 'culture'           # default: famous landmarks in morning

    def generate(self, location, days=3):
        geo = self.geocode_location(location)
        if not geo:
            print("❌ Location not found! Try 'City, Country' format.")
            sys.exit(1)

        print(f"📍 Found: {geo['display_name']}")
        attractions = self.collect_attractions(geo['lat'], geo['lon'])

        # Bucket by time-of-day suitability
        buckets = {'culture': [], 'outdoors': [], 'evening': []}
        for a in attractions:
            buckets[self.categorize(a)].append(a)

        slots = [('09:00', 'Morning', 'culture'),
                 ('13:00', 'Afternoon', 'outdoors'),
                 ('18:00', 'Evening', 'evening')]

        itinerary = {
            'destination': location,
            'country': geo['country'],
            'days': []
        }
        # Track used places per bucket to prevent repeats
        cursor = {'culture': 0, 'outdoors': 0, 'evening': 0}

        for d in range(1, days + 1):
            day_plan = {'day': d, 'activities': []}
            for time, period, bucket in slots:
                pool = buckets[bucket]
                if pool:
                    idx = cursor[bucket] % len(pool)
                    att = pool[idx]
                    cursor[bucket] += 1
                    entry = {
                        'time': time, 'period': period,
                        'activity': att['name'],
                        'source': att['source'],
                        'image': att.get('image')
                    }
                else:
                    # HONEST fallback: activity TYPE, never a fake place name
                    generic = {
                        'culture': f'Explore a historic neighborhood of {geo["city"] or location}',
                        'outdoors': f'Walk through a local park or garden in {geo["city"] or location}',
                        'evening': f'Dinner at a well-reviewed local restaurant (check Google Maps ratings near you)'
                    }
                    entry = {
                        'time': time, 'period': period,
                        'activity': generic[bucket],
                        'source': 'suggestion',
                        'image': None
                    }
                day_plan['activities'].append(entry)
            itinerary['days'].append(day_plan)

        itinerary['hotels'] = self.get_hotels(geo['lat'], geo['lon'])
        itinerary['famous_food'] = self.get_famous_food(geo)
        return itinerary

    # ---------------------------------------------------------------
    # Hotels: real OSM data, ranked by star rating when available.
    # ---------------------------------------------------------------
    def get_hotels(self, lat, lon):
        try:
            query = f"""
            [out:json][timeout:25];
            (
              node["tourism"~"hotel|guest_house|hostel"](around:5000,{lat},{lon});
            );
            out body 20;"""
            r = self.session.post(
                "https://overpass-api.de/api/interpreter",
                data={'data': query}, timeout=30
            )
            hotels = []
            for el in r.json().get('elements', []):
                tags = el.get('tags', {})
                if 'name' in tags:
                    hotels.append({
                        'name': tags['name'],
                        'stars': tags.get('stars', ''),
                        'type': tags.get('tourism', 'hotel')
                    })
            hotels.sort(key=lambda h: int(h['stars']) if h['stars'].isdigit() else 0,
                        reverse=True)
            return hotels[:5]
        except Exception:
            return []

    # ---------------------------------------------------------------
    # Famous food: country cuisine first, then city.
    # ---------------------------------------------------------------
    def get_famous_food(self, geo):
        try:
            for query in [f"{geo['country']} cuisine",
                          f"{geo['city']} cuisine"]:
                if not query.strip():
                    continue
                clean = urllib.parse.quote(query.replace(' ', '_'))
                url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{clean}"
                r = self.session.get(url, timeout=8)
                if r.status_code == 200:
                    extract = r.json().get('extract', '')
                    if len(extract) > 80:
                        return extract[:500]
        except Exception:
            pass
        return (f"Explore the traditional cuisine of {geo['country'] or geo['display_name']}. "
                f"Ask your hotel for the best local restaurants.")


def export_html(plan, filename):
    html = f"""<html><head><title>Trip to {plan['destination']}</title>
<style>body{{font-family:Arial;max-width:800px;margin:auto;padding:20px}}
img{{border-radius:8px;margin:5px 0}} .src{{color:#888;font-size:0.85em}}</style>
</head><body>
<h1>🌍 {plan['destination']}</h1>"""
    for day in plan['days']:
        html += f"<h2>📅 Day {day['day']}</h2>"
        for act in day['activities']:
            html += f"<h3>{act['time']} — {act['activity']}</h3>"
            html += f"<div class='src'>source: {act['source']}</div>"
            if act.get('image'):
                html += f"<img src='{act['image']}' width='350'><br>"
    html += f"<h2>🏨 Hotels</h2><ul>"
    for h in plan['hotels']:
        stars = f" ⭐{h['stars']}" if h['stars'] else ""
        html += f"<li><b>{h['name']}</b>{stars} ({h['type']})</li>"
    if not plan['hotels']:
        html += "<li>Search Booking.com for central options</li>"
    html += f"</ul><h2>🍜 Famous Food</h2><p>{plan['famous_food']}</p></body></html>"
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(html)


def main():
    print("=" * 55)
    print("🌍 TRAVEL ITINERARY GENERATOR v3.0")
    print("=" * 55)

    location = input("📍 Destination (e.g., 'Mumbai, India'): ").strip()
    if not location:
        print("Please enter a location!")
        return
    try:
        days = int(input("📅 Days? (default 3): ") or "3")
    except ValueError:
        days = 3

    gen = TravelItineraryGenerator()
    plan = gen.generate(location, days)

    print(f"\n{'=' * 55}\n🎒 {location.upper()} — {days} DAYS\n{'=' * 55}")
    print("\n🏨 HOTELS:")
    for h in plan['hotels']:
        stars = f" ⭐{h['stars']}" if h['stars'] else ""
        print(f"  • {h['name']}{stars}")
    if not plan['hotels']:
        print("  • Check Booking.com for central stays")

    print(f"\n🍜 FAMOUS FOOD: {plan['famous_food'][:200]}...")

    for day in plan['days']:
        print(f"\n📅 Day {day['day']}")
        for act in day['activities']:
            print(f"  {act['time']} — {act['activity']} [{act['source']}]")

    safe = location.replace(' ', '_').replace(',', '')
    json_file = f"itinerary_{safe}.json"
    html_file = f"itinerary_{safe}.html"
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(plan, f, indent=2, ensure_ascii=False)
    export_html(plan, html_file)
    print(f"\n💾 Saved: {json_file}, {html_file}")
    print("   Double-click the .html file to see your trip with photos!")


if __name__ == "__main__":
    main()
