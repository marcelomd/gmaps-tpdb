#!/usr/bin/env python
"""
Test specific query combinations for the compounds API
"""
import requests
import json
from requests.sessions import Session

BASE_URL = "http://localhost:8001"
LOGIN_URL = f"{BASE_URL}/accounts/login/"
API_URL = f"{BASE_URL}/api/compounds/"

def login_session():
    session = Session()
    
    # Get CSRF token
    login_page = session.get(LOGIN_URL)
    csrf_token = None
    for line in login_page.text.split('\n'):
        if 'csrfmiddlewaretoken' in line:
            start = line.find('value="') + 7
            end = line.find('"', start)
            csrf_token = line[start:end]
            break
    
    # Login
    login_data = {
        'email': 'testapi@example.com',
        'password': 'testpass123',
        'csrfmiddlewaretoken': csrf_token
    }
    session.post(LOGIN_URL, data=login_data)
    return session

def test_queries():
    session = login_session()
    
    print("=== Testing Specific Query Combinations ===\n")
    
    # Test 1: All compounds from a given class (using class name)
    print("1. All compounds from 'Fluoroquinolone' class:")
    response = session.get(f"{API_URL}?class_name=Fluoroquinolone&page_size=3")
    if response.status_code == 200:
        data = response.json()
        total = data.get('pagination', {}).get('total', 0)
        print(f"   Found {total} compounds in Fluoroquinolone class")
        for compound in data.get('data', [])[:2]:  # Show first 2
            print(f"   - {compound['name']} (Type: {compound['type']})")
    print()
    
    # Test 2: All TP compounds from a given original compound
    print("2. All TP compounds from 'ciprofloxacin (cip)' original:")
    # First, get the original compound ID
    orig_response = session.get(f"{API_URL}?name=ciprofloxacin&type=original")
    if orig_response.status_code == 200:
        orig_data = orig_response.json()
        if orig_data.get('data'):
            origin_id = orig_data['data'][0]['id']
            print(f"   Original compound ID: {origin_id}")
            
            # Now get TP compounds from this origin
            tp_response = session.get(f"{API_URL}?type=TP&origin_id={origin_id}&page_size=5")
            if tp_response.status_code == 200:
                tp_data = tp_response.json()
                total = tp_data.get('pagination', {}).get('total', 0)
                print(f"   Found {total} TP compounds from ciprofloxacin")
                for compound in tp_data.get('data', [])[:3]:  # Show first 3
                    print(f"   - {compound['name']} (Treatments: {len(compound['treatments'])})")
    print()
    
    # Test 3: TP compounds with a given treatment
    print("3. TP compounds with 'Heat' treatment:")
    response = session.get(f"{API_URL}?type=TP&treatment_name=Heat&page_size=5")
    if response.status_code == 200:
        data = response.json()
        total = data.get('pagination', {}).get('total', 0)
        print(f"   Found {total} TP compounds with Heat treatment")
        for compound in data.get('data', [])[:3]:  # Show first 3
            treatments = [t['name'] for t in compound['treatments']]
            print(f"   - {compound['name']} (Treatments: {treatments})")
    print()
    
    # Test 4: Complex combination - TP compounds from Fluoroquinolone class with specific treatment
    print("4. TP compounds from Fluoroquinolone class with Heat treatment:")
    response = session.get(f"{API_URL}?class_name=Fluoroquinolone&type=TP&treatment_name=Heat&page_size=5")
    if response.status_code == 200:
        data = response.json()
        total = data.get('pagination', {}).get('total', 0)
        print(f"   Found {total} TP compounds matching all criteria")
        query_info = data.get('query', {})
        print(f"   Applied filters: {query_info}")
        for compound in data.get('data', [])[:3]:  # Show first 3
            print(f"   - {compound['name']} in {compound['class']['name']}")
    print()
    
    # Test 5: Get specific compound by ID
    print("5. Get specific compound by ID:")
    # Get first compound ID
    response = session.get(f"{API_URL}?page_size=1")
    if response.status_code == 200:
        data = response.json()
        if data.get('data'):
            compound_id = data['data'][0]['id']
            
            # Get details for this specific compound
            detail_response = session.get(f"{API_URL}?compound_id={compound_id}")
            if detail_response.status_code == 200:
                detail_data = detail_response.json()
                compound = detail_data['data'][0]
                print(f"   Compound: {compound['name']}")
                print(f"   Type: {compound['type']}")
                print(f"   Formula: {compound['neutral_formula']}")
                print(f"   Class: {compound['class']['name']}")
                print(f"   Subclass: {compound['subclass']['name']}")
                print(f"   References: {len(compound.get('references', []))}")
    print()
    
    # Test 6: Error handling - invalid ID
    print("6. Error handling - invalid compound ID:")
    response = session.get(f"{API_URL}?compound_id=invalid-uuid")
    print(f"   Status: {response.status_code}")
    if response.status_code == 400:
        error_data = response.json()
        print(f"   Error: {error_data.get('message')}")

if __name__ == "__main__":
    test_queries()