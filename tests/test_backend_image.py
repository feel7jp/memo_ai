import requests
import base64
import json

# Create a small 1x1 transparent PNG for testing
# 1x1 pixel PNG
image_data = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82'
b64_image = base64.b64encode(image_data).decode('utf-8')

payload = {
    "text": "What is in this image?",
    "target_id": "test-db-id",
    "system_prompt": "You are a helpful assistant.",
    "session_history": [],
    "image_data": b64_image,
    "image_mime_type": "image/png"
}

try:
    print("Sending request to http://localhost:8000/api/chat...")
    response = requests.post("http://localhost:8000/api/chat", json=payload)
    
    print(f"Status Code: {response.status_code}")
    if response.status_code == 200:
        print("Response:", response.json())
    else:
        print("Error Response:", response.text)

except Exception as e:
    print("Failed to connect:", e)
