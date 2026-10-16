#!/usr/bin/env python3
import requests
import json
import sys
import urllib.parse

class TravelItineraryGenerator:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': 'TravelBot/1.0'})
    
    def geocode_location(self, location_name):
        try:
            url = "https://nominatim.openstreetmap.org/search"
            params = {'q': location_name, 'format': 'json', 'limit': 1}
            response = self.session.get(url, params=params)
            data = response.json()
            if data:
                return {
                    'display_name': data[0]['display_name'],
                    'lat': float(data[0]['lat']),
                    'lon': float(data[0]['lon'])
                }
            return None
        except Exception as e:
            print(f"Error: {e}")
            return None
    
    def get_image(self, name, fallback_image=None):
        """Get image from Wikipedia. Falls back to destination image if not found."""
        try:
            clean = urllib.parse.quote(name.replace(" ", "_"))
            url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{clean}"
            response = self.session.get(url, timeout=5)
            if response.status_code == 200:
                data = response.json()
                thumb = data.get('thumbnail', {}).get('source')
                if thumb:
                    return thumb
        except:
            pass
        return fallback_image  # Use destination image as fallback
    
    def get_destination_info(self, location):
        """Get destination overview + image"""
        try:
            clean = urllib.parse.quote(location.replace(" ", "_"))
            url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{clean}"
            response = self.session.get(url, timeout=5)
            if response.status_code == 200:
                data = response.json()
                return {
                    'description': data.get('description', 'Travel Destination'),
                    'extract': data.get('extract', '')[:400],
                    'image': data.get('thumbnail', {}).get('source', None)
                }
        except:
            pass
        return {'description': 'Travel Destination', 'extract': '', 'image': None}
    
    def get_famous_food(self, location):
        """Get famous food from Wikipedia cuisine article"""
        try:
            for query in [f"{location} cuisine", f"Cuisine of {location}"]:
                clean = urllib.parse.quote(query.replace(" ", "_"))
                url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{clean}"
                response = self.session.get(url, timeout=5)
                if response.status_code == 200:
                    data = response.json()
                    extract = data.get('extract', '')
                    if len(extract) > 50:
                        return extract[:500]
        except:
            pass
        return f"Try local street food, traditional restaurants, and famous regional dishes of {location}. Ask locals for their favorite spots!"
    
    def get_attractions(self, lat, lon):
        try:
            url = "https://overpass-api.de/api/interpreter"
            query = f"""
            [out:json][timeout:25];
            (
              node["tourism"~"attraction|museum|viewpoint|gallery|zoo"](around:8000,{lat},{lon});
              node["historic"~"monument|castle|ruins|church|temple"](around:8000,{lat},{lon});
              node["leisure"~"park|garden|beach"](around:8000,{lat},{lon});
            );
            out body 50;
            """
            response = self.session.post(url, data={'data': query})
            data = response.json()
            attractions = []
            for el in data.get('elements', []):
                if 'tags' in el and 'name' in el['tags']:
                    attractions.append({
                        'name': el['tags']['name'],
                        'type': el['tags'].get('tourism', el['tags'].get('historic', 'attraction'))
                    })
            seen = set()
            unique = []
            for att in attractions:
                if att['name'] not in seen:
                    seen.add(att['name'])
                    unique.append(att)
            return unique[:20] if unique else self._defaults()
        except:
            return self._defaults()
    
    def get_hotels(self, lat, lon):
        """Find real hotels near destination"""
        try:
            url = "https://overpass-api.de/api/interpreter"
            query = f"""
            [out:json][timeout:25];
            (
              node["tourism"="hotel"](around:5000,{lat},{lon});
              node["tourism"="guest_house"](around:5000,{lat},{lon});
              node["tourism"="hostel"](around:5000,{lat},{lon});
            );
            out body 15;
            """
            response = self.session.post(url, data={'data': query})
            data = response.json()
            hotels = []
            for el in data.get('elements', []):
                if 'tags' in el and 'name' in el['tags']:
                    stars = el['tags'].get('stars', '')
                    hotels.append({
                        'name': el['tags']['name'],
                        'type': el['tags'].get('tourism', 'hotel'),
                        'stars': stars,
                        'location': 'Near city center'
                    })
            return hotels[:5]
        except:
            return []
    
    def _defaults(self):
        return [
            {'name': 'Old Town Center', 'type': 'historic'},
            {'name': 'Central Museum', 'type': 'museum'},
            {'name': 'City Park', 'type': 'park'},
            {'name': 'Local Market', 'type': 'market'},
            {'name': 'Main Viewpoint', 'type': 'viewpoint'},
            {'name': 'Historic Castle', 'type': 'historic'},
            {'name': 'Art Gallery', 'type': 'gallery'},
            {'name': 'Botanical Garden', 'type': 'garden'},
            {'name': 'Ancient Temple', 'type': 'historic'},
            {'name': 'Shopping District', 'type': 'shopping'},
            {'name': 'Riverside Walk', 'type': 'nature'},
            {'name': 'Local Theater', 'type': 'entertainment'},
            {'name': 'Street Food Area', 'type': 'food'},
            {'name': 'Science Center', 'type': 'museum'},
            {'name': 'Harbor District', 'type': 'attraction'},
            {'name': 'Mountain Overlook', 'type': 'viewpoint'},
            {'name': 'Traditional Quarter', 'type': 'cultural'},
            {'name': 'Modern Art Museum', 'type': 'museum'},
            {'name': 'City Zoo', 'type': 'zoo'},
            {'name': 'Night Market', 'type': 'market'}
        ]
    
    def generate(self, location, days=3):
        geo = self.geocode_location(location)
        if not geo:
            print("Location not found!")
            sys.exit(1)
        
        print(f"Found: {geo['display_name']}")
        print("Fetching images, hotels & food info...")
        
        attractions = self.get_attractions(geo['lat'], geo['lon'])
        dest_info = self.get_destination_info(location)
        fallback_img = dest_info.get('image')
        hotels = self.get_hotels(geo['lat'], geo['lon'])
        food = self.get_famous_food(location)
        
        itinerary = {
            'destination': location,
            'description': dest_info['description'],
            'destination_image': fallback_img,
            'famous_food': food,
            'hotels': hotels,
            'days': []
        }
        slots = [("09:00", "Morning"), ("13:00", "Afternoon"), ("18:00", "Evening")]
        
        for d in range(1, days + 1):
            day_plan = {'day': d, 'activities': []}
            for i, (time, period) in enumerate(slots):
                idx = (d-1) * 3 + i
                att = attractions[idx] if idx < len(attractions) else attractions[(idx + d) % len(attractions)]
                
                # Get image for this attraction
                image = self.get_image(att['name'], fallback_img)
                
                day_plan['activities'].append({
                    'time': time,
                    'period': period,
                    'activity': att['name'],
                    'type': att['type'],
                    'image': image
                })
            itinerary['days'].append(day_plan)
        
        return itinerary

def main():
    print("=" * 50)
    print("TRAVEL ITINERARY GENERATOR")
    print("=" * 50)
    
    location = input("Enter destination (e.g., 'Paris, France'): ").strip()
    if not location:
        print("Please enter a location!")
        return
    
    try:
        days = int(input("How many days? (default 3): ") or "3")
    except:
        days = 3
    
    gen = TravelItineraryGenerator()
    plan = gen.generate(location, days)
    
    print(f"\n{'=' * 50}")
    print(f"ITINERARY FOR {location.upper()}")
    print(f"{'=' * 50}")
    
    # Show destination image link
    if plan['destination_image']:
        print(f"\n📷 Destination Photo: {plan['destination_image']}")
    
    # Show hotels
    print(f"\n🏨 RECOMMENDED HOTELS:")
    if plan['hotels']:
        for h in plan['hotels']:
            stars = f" ({h['stars']} stars)" if h['stars'] else ""
            print(f"  • {h['name']}{stars} [{h['type']}]")
    else:
        print("  • Search Booking.com or Airbnb for best options near city center")
    
    # Show famous food
    print(f"\n🍜 FAMOUS FOOD OF {location.upper()}:")
    print(f"  {plan['famous_food'][:250]}...")
    
    # Show itinerary
    for day in plan['days']:
        print(f"\n📅 Day {day['day']}:")
        for act in day['activities']:
            print(f"  {act['time']} - {act['activity']} ({act['type']})")
            if act['image']:
                print(f"      📷 {act['image']}")
    
    filename = f"itinerary_{location.replace(' ', '_').replace(',', '')}.json"
    with open(filename, 'w') as f:
        json.dump(plan, f, indent=2)
    print(f"\n💾 Saved to: {filename}")
    print("\n✨ Open the .json file to see all image links! ✨")

if __name__ == "__main__":
    main()
