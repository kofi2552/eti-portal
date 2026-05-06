import requests
import json
import uuid

# Replace this with the API key you generated
API_KEY = "8d64228bec94e862af08626dc0f4c5041545f499722feeb5f3cbcf193c90f50d"

# Make sure this matches the base URL where your Django app is running locally
BASE_URL = "http://127.0.0.1:8000/finance" 

# The student ID you want to test with (must exist in your local DB!)
TEST_STUDENT_ID = "STU263368" 

headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

def test_validate_student():
    print(f"\n==============================================")
    print(f"1. Testing Validate Student: {TEST_STUDENT_ID}")
    print(f"==============================================")
    
    url = f"{BASE_URL}/api/bank/students/validate/"
    payload = {"student_id": TEST_STUDENT_ID}
    
    response = requests.post(url, json=payload, headers=headers)
    print(f"Status Code: {response.status_code}")
    try:
        print(f"Response: {json.dumps(response.json(), indent=2)}")
    except:
        print(f"Response Text: {response.text}")

def test_notify_payment():
    print(f"\n==============================================")
    print(f"2. Testing Notify Payment (Webhook)")
    print(f"==============================================")
    
    url = f"{BASE_URL}/api/bank/payments/notify/"
    
    # Generate a random transaction ID each time this script runs
    reference_id = f"BANK-{uuid.uuid4().hex[:8].upper()}"
    
    payload = {
        "bank_reference_id": reference_id,
        "student_id": TEST_STUDENT_ID,
        "total_amount_paid": "1100.00",
        "fee_breakdown": [
            {"component_code": "Tuition", "amount": "1000.00"},
            {"component_code": "Library", "amount": "100.00"}
        ]
    }
    
    print(f"Sending Payload:")
    print(json.dumps(payload, indent=2))
    print("-" * 40)
    
    response = requests.post(url, json=payload, headers=headers)
    print(f"Status Code: {response.status_code}")
    try:
        print(f"Response: {json.dumps(response.json(), indent=2)}")
    except:
        print(f"Response Text: {response.text}")

if __name__ == "__main__":
    test_validate_student()
    test_notify_payment()
