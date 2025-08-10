#!/usr/bin/env python
"""
Test script for the compounds API endpoints
"""
import requests
import json
from requests.sessions import Session

BASE_URL = "http://localhost:8001"
LOGIN_URL = f"{BASE_URL}/accounts/login/"
API_URL = f"{BASE_URL}/api/compounds/"
METADATA_URL = f"{BASE_URL}/api/metadata/"

def test_api():
    # Create session for persistent cookies
    session = Session()
    
    # First, get the login page to get CSRF token
    print("Getting login page...")
    login_page = session.get(LOGIN_URL)
    
    if login_page.status_code != 200:
        print(f"Failed to get login page: {login_page.status_code}")
        return
    
    # Extract CSRF token (basic extraction)
    csrf_token = None
    for line in login_page.text.split('\n'):
        if 'csrfmiddlewaretoken' in line:
            start = line.find('value="') + 7
            end = line.find('"', start)
            csrf_token = line[start:end]
            break
    
    if not csrf_token:
        print("Could not find CSRF token")
        return
    
    print(f"Found CSRF token: {csrf_token[:20]}...")
    
    # Login
    print("Logging in...")
    login_data = {
        'email': 'testapi@example.com',
        'password': 'testpass123',
        'csrfmiddlewaretoken': csrf_token
    }
    
    login_response = session.post(LOGIN_URL, data=login_data)
    print(f"Login response status: {login_response.status_code}")
    
    # Test metadata endpoint
    print("\n--- Testing metadata endpoint ---")
    metadata_response = session.get(METADATA_URL)
    print(f"Metadata status: {metadata_response.status_code}")
    if metadata_response.status_code == 200:
        metadata = metadata_response.json()
        print(f"Status: {metadata.get('status')}")
        data = metadata.get('data', {})
        print(f"Classes count: {len(data.get('classes', []))}")
        print(f"Subclasses count: {len(data.get('subclasses', []))}")
        print(f"Treatments count: {len(data.get('treatments', []))}")
        print(f"Compound types: {data.get('compound_types', [])}")
    else:
        print(f"Error: {metadata_response.text}")
    
    # Test compounds endpoint
    print("\n--- Testing compounds endpoint ---")
    compounds_response = session.get(API_URL)
    print(f"Compounds status: {compounds_response.status_code}")
    if compounds_response.status_code == 200:
        compounds = compounds_response.json()
        print(f"Status: {compounds.get('status')}")
        print(f"Total compounds: {compounds.get('pagination', {}).get('total', 0)}")
        print(f"Results in this page: {len(compounds.get('data', []))}")
        
        # Print first compound if available
        data = compounds.get('data', [])
        if data:
            first_compound = data[0]
            print(f"First compound: {first_compound.get('name')} (Type: {first_compound.get('type')})")
    else:
        print(f"Error: {compounds_response.text}")
    
    # Test specific queries
    print("\n--- Testing specific queries ---")
    
    # Test type filter
    print("Testing TP compounds...")
    tp_response = session.get(f"{API_URL}?type=TP")
    if tp_response.status_code == 200:
        tp_data = tp_response.json()
        print(f"TP compounds found: {tp_data.get('pagination', {}).get('total', 0)}")
    
    # Test pagination
    print("Testing pagination...")
    page_response = session.get(f"{API_URL}?page_size=5&page=1")
    if page_response.status_code == 200:
        page_data = page_response.json()
        pagination = page_data.get('pagination', {})
        print(f"Page 1, size 5: {len(page_data.get('data', []))} results")
        print(f"Total pages: {pagination.get('total_pages')}")
        print(f"Has next: {pagination.get('has_next')}")

if __name__ == "__main__":
    test_api()