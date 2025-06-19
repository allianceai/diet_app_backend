import os
import base64
import json
from flask import Flask, request, jsonify
import requests
from datetime import datetime, timedelta
from flask_cors import CORS
# --------------------------------------------------------------------------
# Optionally load environment variables from a .env file if desired.
# pip install python-dotenv
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

app = Flask(__name__)
CORS(app)
# Read your FatSecret credentials from environment variables (or hardcode).
FATSECRET_CLIENT_ID = os.getenv('FATSECRET_CLIENT_ID', 'YOUR_CLIENT_ID')
FATSECRET_CLIENT_SECRET = os.getenv('FATSECRET_CLIENT_SECRET', 'YOUR_CLIENT_SECRET')

# We'll store these in Python memory for demo. In production,
# you'd likely store them elsewhere.
cached_token = None
token_expiry = None

@app.route('/fatsecret_token', methods=['GET'])
def get_fatsecret_token():
    """
    Endpoint to retrieve (and cache) a FatSecret API OAuth2 token.
    """
    global cached_token, token_expiry

    if cached_token and token_expiry and datetime.now() < token_expiry:
        return jsonify({
            'access_token': cached_token,
            'expires_in': (token_expiry - datetime.now()).seconds
        }), 200

    token_url = "https://oauth.fatsecret.com/connect/token"
    auth_string = base64.b64encode(f"{FATSECRET_CLIENT_ID}:{FATSECRET_CLIENT_SECRET}".encode("utf-8")).decode("utf-8")

    headers = {
        "Authorization": f"Basic {auth_string}",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    # Updated scope to include 'barcode' for barcode scanning
    # Add other scopes like 'image-recognition' or 'premier' if your key has access and you plan to use them.
    body = "grant_type=client_credentials&scope=basic barcode" # MODIFIED

    try:
        response = requests.post(token_url, headers=headers, data=body)
        if response.status_code == 200:
            data = json.loads(response.text)
            cached_token = data['access_token']
            expires_in = data['expires_in']
            token_expiry = datetime.now() + timedelta(seconds=expires_in)
            return jsonify({
                'access_token': cached_token,
                'expires_in': expires_in
            }), 200
        else:
            error_details = response.text
            try:
                error_json = response.json()
                if 'error_description' in error_json:
                    error_details = error_json['error_description']
                elif 'error' in error_json:
                    error_details = error_json['error']
            except ValueError:
                pass # Keep original response.text if not JSON
            print(f"FatSecret token request failed with status {response.status_code}: {error_details}")
            return jsonify({
                'error': f"FatSecret token request failed: {response.status_code}",
                'details': error_details
            }), 400
    except Exception as e:
        print(f"Exception during token fetch: {str(e)}")
        return jsonify({
            'error': 'Exception during token fetch',
            'details': str(e)
        }), 500

@app.route('/fatsecret_search', methods=['POST'])
def search_foods():
    """
    Proxy endpoint for FatSecret food search to avoid CORS issues in web browsers.
    Flutter calls this endpoint instead of calling FatSecret directly.
    """
    global cached_token, token_expiry
    
    # Get the search query from the request
    data = request.json
    if not data:
        return jsonify({
            'error': 'No JSON data received'
        }), 400
        
    query = data.get('query', '')
    if not query:
        return jsonify({
            'error': 'No search query provided'
        }), 400
        
    page_number = data.get('page_number', '0')
    max_results = data.get('max_results', '10')
    
    # Ensure we have a valid token
    if not cached_token or not token_expiry or datetime.now() >= token_expiry:
        # Get a new token if needed
        try:
            token_response = get_fatsecret_token()
            if isinstance(token_response, tuple) and token_response[1] != 200:
                return token_response
        except Exception as e:
            return jsonify({
                'error': 'Failed to get token',
                'details': str(e)
            }), 500
    
    # Call FatSecret API
    fatsecret_url = "https://platform.fatsecret.com/rest/server.api"
    headers = {
        "Authorization": f"Bearer {cached_token}",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    
    # Create form data instead of JSON payload
    # Use foods.search instead of foods.search.v2 (which might require premier scope)
    form_data = {
        "method": "foods.search",
        "search_expression": query,
        "format": "json",
        "page_number": page_number,
        "max_results": max_results
    }
    
    try:
        print(f"Sending request to FatSecret with query: {query}")
        # Use data parameter for form data instead of json parameter
        response = requests.post(fatsecret_url, headers=headers, data=form_data)
        print(f"FatSecret response status: {response.status_code}")
        
        # Print the first part of the response for debugging
        response_preview = response.text[:min(500, len(response.text))]
        print(f"FatSecret response preview: {response_preview}")
        
        if response.status_code != 200:
            return jsonify({
                'error': f'FatSecret API returned status {response.status_code}',
                'details': response.text
            }), response.status_code
            
        # Try to parse the response as JSON
        response_data = response.json()
        return jsonify(response_data), 200
    except requests.RequestException as e:
        print(f"Request exception: {str(e)}")
        return jsonify({
            'error': 'Exception during FatSecret search request',
            'details': str(e)
        }), 500
    except json.JSONDecodeError as e:
        print(f"JSON decode error: {str(e)}")
        print(f"Raw response: {response.text}")
        return jsonify({
            'error': 'Failed to parse FatSecret response as JSON',
            'details': str(e),
            'response': response.text
        }), 500
    except Exception as e:
        print(f"Unexpected error: {str(e)}")
        return jsonify({
            'error': 'Unexpected exception during FatSecret search',
            'details': str(e)
        }), 500

@app.route('/fatsecret_food_details', methods=['POST'])
def get_food_details():
    """
    Proxy endpoint for FatSecret food details to avoid CORS issues in web browsers.
    Flutter calls this endpoint instead of calling FatSecret directly.
    """
    global cached_token, token_expiry
    
    # Get the food ID from the request
    data = request.json
    if not data:
        return jsonify({
            'error': 'No JSON data received'
        }), 400
        
    food_id = data.get('food_id', '')
    if not food_id:
        return jsonify({
            'error': 'No food ID provided'
        }), 400
    
    # Ensure we have a valid token
    if not cached_token or not token_expiry or datetime.now() >= token_expiry:
        # Get a new token if needed
        try:
            token_response = get_fatsecret_token()
            if isinstance(token_response, tuple) and token_response[1] != 200:
                return token_response
        except Exception as e:
            return jsonify({
                'error': 'Failed to get token',
                'details': str(e)
            }), 500
    
    # Call FatSecret API
    fatsecret_url = "https://platform.fatsecret.com/rest/server.api"
    headers = {
        "Authorization": f"Bearer {cached_token}",
        "Content-Type": "application/x-www-form-urlencoded"  # Changed from application/json
    }
    
    # Create form data instead of JSON payload
    form_data = {
        "method": "food.get.v2",  # Using v2 instead of v4 which might require premier
        "food_id": food_id,
        "format": "json"
    }
    
    try:
        print(f"Sending food details request to FatSecret for food ID: {food_id}")
        # Use data parameter for form data instead of json parameter
        response = requests.post(fatsecret_url, headers=headers, data=form_data)
        print(f"FatSecret food details response status: {response.status_code}")
        
        # Print the first part of the response for debugging
        response_preview = response.text[:min(500, len(response.text))]
        print(f"FatSecret food details response preview: {response_preview}")
        
        if response.status_code != 200:
            return jsonify({
                'error': f'FatSecret API returned status {response.status_code}',
                'details': response.text
            }), response.status_code
            
        # Try to parse the response as JSON
        response_data = response.json()
        return jsonify(response_data), 200
    except requests.RequestException as e:
        print(f"Request exception: {str(e)}")
        return jsonify({
            'error': 'Exception during FatSecret food details request',
            'details': str(e)
        }), 500
    except json.JSONDecodeError as e:
        print(f"JSON decode error: {str(e)}")
        print(f"Raw response: {response.text}")
        return jsonify({
            'error': 'Failed to parse FatSecret food details response as JSON',
            'details': str(e),
            'response': response.text
        }), 500
    except Exception as e:
        print(f"Unexpected error: {str(e)}")
        return jsonify({
            'error': 'Unexpected exception during FatSecret food details fetch',
            'details': str(e)
        }), 500

@app.route('/fatsecret_image_recognition', methods=['POST'])
def recognize_food_from_image():
    """
    Proxy endpoint for FatSecret's image recognition API.
    This endpoint accepts an image file and sends it to FatSecret for food recognition.
    """
    global cached_token, token_expiry
    
    # Check if an image file was uploaded
    if 'image' not in request.files:
        return jsonify({
            'error': 'No image file provided'
        }), 400
        
    image_file = request.files['image']
    if image_file.filename == '':
        return jsonify({
            'error': 'Empty image file'
        }), 400
    
    # Ensure we have a valid token
    if not cached_token or not token_expiry or datetime.now() >= token_expiry:
        # Get a new token if needed
        try:
            token_response = get_fatsecret_token()
            if isinstance(token_response, tuple) and token_response[1] != 200:
                return token_response
        except Exception as e:
            return jsonify({
                'error': 'Failed to get token',
                'details': str(e)
            }), 500
    
    # Call FatSecret Image Recognition API
    fatsecret_url = "https://platform.fatsecret.com/rest/server.api"
    headers = {
        "Authorization": f"Bearer {cached_token}"
    }
    
    try:
        print("Sending image recognition request to FatSecret")
        
        # Create a multipart form-data request
        files = {
            'method': (None, 'food.recognize'),
            'format': (None, 'json'),
            'image': (image_file.filename, image_file.read(), image_file.content_type)
        }
        
        response = requests.post(fatsecret_url, headers=headers, files=files)
        print(f"FatSecret image recognition response status: {response.status_code}")
        
        # Print the first part of the response for debugging
        response_preview = response.text[:min(500, len(response.text))]
        print(f"FatSecret image recognition response preview: {response_preview}")
        
        if response.status_code != 200:
            return jsonify({
                'error': f'FatSecret API returned status {response.status_code}',
                'details': response.text
            }), response.status_code
            
        # Try to parse the response as JSON
        response_data = response.json()
        return jsonify(response_data), 200
    except requests.RequestException as e:
        print(f"Request exception: {str(e)}")
        return jsonify({
            'error': 'Exception during FatSecret image recognition request',
            'details': str(e)
        }), 500
    except json.JSONDecodeError as e:
        print(f"JSON decode error: {str(e)}")
        print(f"Raw response: {response.text}")
        return jsonify({
            'error': 'Failed to parse FatSecret image recognition response as JSON',
            'details': str(e),
            'response': response.text
        }), 500
    except Exception as e:
        print(f"Unexpected error: {str(e)}")
        return jsonify({
            'error': 'Unexpected exception during FatSecret image recognition',
            'details': str(e)
        }), 500

@app.route('/fatsecret_barcode_lookup', methods=['POST'])
def lookup_barcode():
    """
    Proxy endpoint for FatSecret food.find_id_for_barcode.
    """
    global cached_token, token_expiry

    data = request.json
    if not data:
        return jsonify({'error': 'No JSON data received'}), 400
        
    barcode = data.get('barcode', '')
    if not barcode:
        return jsonify({'error': 'No barcode provided'}), 400

    # Ensure we have a valid token
    if not cached_token or not token_expiry or datetime.now() >= token_expiry:
        try:
            token_response_tuple = get_fatsecret_token() # get_fatsecret_token returns a tuple
            token_data = token_response_tuple[0].get_json() if token_response_tuple[0] else None
            status_code = token_response_tuple[1]

            if status_code != 200 or not token_data or 'access_token' not in token_data :
                print(f"Failed to refresh token for barcode lookup. Status: {status_code}, Data: {token_data}")
                return jsonify({'error': 'Failed to refresh token for barcode lookup', 'details': token_data.get('details', 'Unknown token error') if token_data else 'Unknown token error'}), status_code
            # cached_token is updated globally by get_fatsecret_token
        except Exception as e:
            print(f"Exception refreshing token for barcode lookup: {str(e)}")
            return jsonify({'error': 'Exception refreshing token', 'details': str(e)}), 500
    
    fatsecret_url = "https://platform.fatsecret.com/rest/server.api"
    headers = {
        "Authorization": f"Bearer {cached_token}",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    form_data = {
        "method": "food.find_id_for_barcode",
        "barcode": barcode,
        "format": "json"
    }

    try:
        print(f"Sending barcode lookup request to FatSecret for barcode: {barcode}")
        response = requests.post(fatsecret_url, headers=headers, data=form_data)
        print(f"FatSecret barcode lookup response status: {response.status_code}")
        response_preview = response.text[:min(500, len(response.text))]
        print(f"FatSecret barcode lookup response preview: {response_preview}")

        if response.status_code != 200:
            return jsonify({
                'error': f'FatSecret API (barcode) returned status {response.status_code}',
                'details': response.text
            }), response.status_code
            
        response_data = response.json()
        # The response for food.find_id_for_barcode is simpler, directly gives food_id and food_name
        # It might be nested under a key like "food_id" -> {"value": "123"} or directly.
        # Check the actual API response structure. Assuming it's:
        # { "food_id": { "value": "..." }, "food_name": { "value": "..." } } or similar
        # OR directly { "food_id": "...", "food_name": "..." }
        if 'food_id' in response_data and response_data['food_id'] and isinstance(response_data['food_id'], dict) and 'value' in response_data['food_id']:
             # This structure is for food.get and other methods, barcode might be simpler
             # For food.find_id_for_barcode, the response is often like:
             # {"food_id": {"value": "FOOD_ID_FOUND"}} if found
             # {"error": {"code": NNN, "message": "No item found."}} if not found
            if 'error' in response_data:
                 return jsonify({'error': 'Food not found for this barcode', 'details': response_data['error']['message']}), 404

            food_id_data = response_data.get('food_id')
            if food_id_data and isinstance(food_id_data, dict) and 'value' in food_id_data:
                food_id_value = food_id_data['value']
                # For barcode scans, you might need to do a subsequent food.get to get the name
                # Or, the user proceeds to FoodDetailsPage which does the food.get
                # For simplicity, we'll just return the ID. FoodDetailsPage will fetch full details.
                return jsonify({'food_id': food_id_value, 'food_name': 'Food Item (Details will be fetched)'}), 200
            else:
                return jsonify({'error': 'Barcode found, but food_id format unexpected', 'details': response_data}), 500

        elif 'error' in response_data: # Handle cases where FatSecret returns an error object
            error_code = response_data['error'].get('code', 'Unknown')
            error_message = response_data['error'].get('message', 'Food not found for this barcode or API error.')
            if error_code == 106 or error_message.lower().contains("no item found"): # Invalid ID or item not found
                return jsonify({'error': 'Food not found for this barcode'}), 404
            return jsonify({'error': error_message, 'details': response_data['error']}), 400
        else:
            # If the structure is completely unexpected or food_id is missing
            print(f"Unexpected response structure from food.find_id_for_barcode: {response_data}")
            return jsonify({'error': 'Food not found or unexpected API response.'}), 404

    except requests.RequestException as e:
        return jsonify({'error': 'Exception during FatSecret barcode lookup', 'details': str(e)}), 500
    except json.JSONDecodeError as e:
        return jsonify({'error': 'Failed to parse FatSecret barcode lookup response', 'details': str(e), 'response': response.text}), 500
    except Exception as e:
        return jsonify({'error': 'Unexpected exception during barcode lookup', 'details': str(e)}), 500

if __name__ == '__main__':
    # Confirm you're using port 5001 if your Dart code is set to 5001
    app.run(host='0.0.0.0', port=5001, debug=True)