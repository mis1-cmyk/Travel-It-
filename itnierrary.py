#!/usr/bin/env python3
import requests
import json
import sys
from datetime import datetime, timedelta

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
    
    def get_attractions(self, lat, lon):
        try:
            url = "https://overpass-api.de/api/interpreter"
            query = f"""
            [out:json][timeout:25];
            (
              node["tourism"~"attraction|museum|viewpoint"](around:5000,{lat},{lon});
              node["historic"~"monument|castle"](around:5000,{lat},{lon});
            );
            out body 15;
            """
            response = self.session.post(url, data={'data': query})
            data = response.json()
            attractions = []
            for el in data.get('elements', []):
                if 'tags' in el and 'name' in el['tags']:
                    attractions.append({
                        'name': el['tags']['name'],
                        'type': el['tags'].get('tourism', 'historic')
                    })
            return attractions[:9] if attractions else self._defaults()
        except:
            return self._defaults()
    
    def _defaults(self):
        return [
            {'name': 'Old Town Center', 'type': 'historic'},
            {'name': 'Central Museum', 'type': 'museum'},
            {'name': 'City Park', 'type': 'attraction'},
            {'name': 'Local Market', 'type': 'attraction'},
            {'name': 'Main Viewpoint', 'type': 'viewpoint'},
            {'name': 'Historic Castle', 'type': 'historic'}
        ]
    
    def generate(self, location, days=3):
        geo = self.geocode_location(location)
        if not geo:
            print("Location not found!")
            sys.exit(1)
        
        print(f"Found: {geo['display_name']}")
        attractions = self.get_attractions(geo['lat'], geo['lon'])
        
        itinerary = {'destination': location, 'days': []}
        slots = [("09:00", "Morning"), ("13:00", "Afternoon"), ("18:00", "Evening")]
        
        for d in range(1, days + 1):
            day_plan = {'day': d, 'activities': []}
            for i, (time, period) in enumerate(slots):
                idx = (d-1)*3 + i
                att = attractions[idx] if idx < len(attractions) else attractions[i % len(attractions)]
                day_plan['activities'].append({
                    'time': time,
                    'period': period,
                    'activity': att['name'],
                    'type': att['type']
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
    
    print(f"\nITINERARY FOR {location.upper()}")
    print("-" * 50)
    for day in plan['days']:
        print(f"\nDay {day['day']}:")
        for act in day['activities']:
            print(f"  {act['time']} - {act['activity']} ({act['type']})")
    
    filename = f"itinerary_{location.replace(' ', '_').replace(',', '')}.json"
    with open(filename, 'w') as f:
        json.dump(plan, f, indent=2)
    print(f"\nSaved to: {filename}")

if __name__ == "__main__":
    main()
