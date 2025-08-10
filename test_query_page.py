#!/usr/bin/env python
"""
Test the query page interface
"""
import requests
from requests.sessions import Session

BASE_URL = "http://localhost:8002"
LOGIN_URL = f"{BASE_URL}/accounts/login/"
QUERY_PAGE_URL = f"{BASE_URL}/query/"
METADATA_URL = f"{BASE_URL}/api/metadata/"
API_URL = f"{BASE_URL}/api/compounds/"

def test_query_page():
    session = Session()
    
    print("=== Testing Query Page Interface ===\n")
    
    # Test 1: Access query page without authentication
    print("1. Testing access without authentication:")
    response = session.get(QUERY_PAGE_URL)
    if response.status_code == 302:
        print("   ✓ Correctly redirects unauthenticated users to login")
    else:
        print(f"   ✗ Unexpected response: {response.status_code}")
    print()
    
    # Test 2: Login and access query page
    print("2. Testing authentication and page access:")
    
    # Get login page and CSRF token
    login_page = session.get(LOGIN_URL)
    csrf_token = None
    for line in login_page.text.split('\n'):
        if 'csrfmiddlewaretoken' in line:
            start = line.find('value="') + 7
            end = line.find('"', start)
            csrf_token = line[start:end]
            break
    
    if csrf_token:
        print(f"   Found CSRF token: {csrf_token[:20]}...")
        
        # Login
        login_data = {
            'email': 'testapi@example.com',
            'password': 'testpass123',
            'csrfmiddlewaretoken': csrf_token
        }
        login_response = session.post(LOGIN_URL, data=login_data)
        print(f"   Login response: {login_response.status_code}")
        
        # Access query page
        query_page = session.get(QUERY_PAGE_URL)
        if query_page.status_code == 200:
            print("   ✓ Successfully accessed query page after login")
            
            # Check if page contains expected elements
            page_content = query_page.text
            checks = [
                ("Form with query fields", "queryForm" in page_content),
                ("Compound name input", 'id="compound_name"' in page_content),
                ("Class dropdown", 'id="class_select"' in page_content),
                ("Treatment dropdown", 'id="treatment_select"' in page_content),
                ("Search button", "Search Compounds" in page_content),
                ("Results section", 'id="results"' in page_content),
                ("jQuery included", "jquery" in page_content.lower()),
                ("User email displayed", "testapi@example.com" in page_content),
            ]
            
            print("   Page content checks:")
            for description, passed in checks:
                status = "✓" if passed else "✗"
                print(f"     {status} {description}")
        else:
            print(f"   ✗ Failed to access query page: {response.status_code}")
    else:
        print("   ✗ Could not find CSRF token")
    print()
    
    # Test 3: Test metadata API endpoint (used by JavaScript)
    print("3. Testing metadata API endpoint:")
    metadata_response = session.get(METADATA_URL)
    if metadata_response.status_code == 200:
        metadata = metadata_response.json()
        if metadata.get('status') == 'success':
            data = metadata.get('data', {})
            print("   ✓ Metadata API working correctly")
            print(f"     Classes: {len(data.get('classes', []))}")
            print(f"     Subclasses: {len(data.get('subclasses', []))}")
            print(f"     Treatments: {len(data.get('treatments', []))}")
            print(f"     Compound types: {data.get('compound_types', [])}")
        else:
            print(f"   ✗ Metadata API error: {metadata.get('message')}")
    else:
        print(f"   ✗ Metadata API failed: {metadata_response.status_code}")
    print()
    
    # Test 4: Test API query functionality
    print("4. Testing API query functionality:")
    api_response = session.get(f"{API_URL}?type=TP&page_size=5")
    if api_response.status_code == 200:
        api_data = api_response.json()
        if api_data.get('status') == 'success':
            print("   ✓ API query working correctly")
            print(f"     Found {api_data.get('pagination', {}).get('total', 0)} TP compounds")
            print(f"     Returned {len(api_data.get('data', []))} results in first page")
        else:
            print(f"   ✗ API query error: {api_data.get('message')}")
    else:
        print(f"   ✗ API query failed: {api_response.status_code}")
    print()
    
    print("=== Query Page Interface Test Complete ===")

if __name__ == "__main__":
    test_query_page()