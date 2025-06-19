from flask import Flask, Response, jsonify
from flask_cors import CORS
import time
import os

app = Flask(__name__)
CORS(app)
LOG_FILE = 'auditoriaEC.log'

@app.route('/logs', methods=['GET'])
def get_logs():
    if not os.path.exists(LOG_FILE):
        return jsonify({'logs': ''})
    with open(LOG_FILE, 'r') as f:
        data = f.read()
    return jsonify({'logs': data})

@app.route('/logs/stream')
def stream_logs():
    def generate():
        if not os.path.exists(LOG_FILE):
            last_size = 0
        else:
            last_size = os.path.getsize(LOG_FILE)
        while True:
            if os.path.exists(LOG_FILE):
                current_size = os.path.getsize(LOG_FILE)
                if current_size > last_size:
                    with open(LOG_FILE, 'r') as f:
                        f.seek(last_size)
                        new_data = f.read()
                    for line in new_data.splitlines():
                        yield f"data: {line}\n\n"
                    last_size = current_size
            time.sleep(1)
    return Response(generate(), mimetype='text/event-stream')

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5003)