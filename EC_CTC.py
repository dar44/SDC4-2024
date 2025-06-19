import requests
import time
import os
from flask import Flask, jsonify, request
from variablesGlobales import  IP_API
import threading
from cryptography.fernet import Fernet

app = Flask(__name__)

# Variables globales para OpenWeather
#API_KEY = APICTC
IP = IP_API
API_KEY_FILE = os.path.join(os.path.dirname(__file__), 'openweather_key.txt')
urlUpdate = f"http://{IP}:5000/update-traffic"
CITY_FILE_PATH = os.path.join(os.path.dirname(__file__), 'cityname.txt')
traffic_status = {"status": "OK"}

def read_api_key():
    try:
        with open(API_KEY_FILE, 'r') as f:
            return f.read().strip()
    except FileNotFoundError:
        return ''

def fetch_temperature_and_update_central():
    while True:
        try:
            with open(CITY_FILE_PATH, 'r') as file:
                CITYNAME = file.read().strip()
            
            api_key = read_api_key()
            url = f'https://api.openweathermap.org/data/2.5/weather?q={CITYNAME}&appid={api_key}'
            response = requests.get(url)
            data = response.json()
            temperature = data['main']['temp'] - 273.15  # Convertir a Celsius
            traffic_status["status"] = "KO" if temperature < 0 else "OK"
            
            # Enviar estado de tráfico al API central
            response = requests.post(urlUpdate, json={"status": traffic_status["status"]})
            print(f"POST to {urlUpdate}: Status {response.status_code}, Response {response.text}")

            print(f"Sent traffic status: {traffic_status['status']} to Central API")
        except Exception as e:
            print(f"Error updating traffic status: {e}")
        time.sleep(10)  # Actualizar cada 10 segundos

@app.route('/traffic_status', methods=['GET'])
def get_traffic_status():
    return jsonify({"traffic_status": traffic_status["status"]})

@app.route('/set_city', methods=['POST'])
def set_city():
    data = request.json
    city = data.get('city')
    if city:
        with open(CITY_FILE_PATH, 'w') as f:
            f.write(city)
        return jsonify({"message": "City updated"})
    return jsonify({"error": "City not provided"}), 400

if __name__ == "__main__":
    threading.Thread(target=fetch_temperature_and_update_central).start()
    app.run(debug=True, host='0.0.0.0', port=5001)