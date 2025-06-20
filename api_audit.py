from flask import Flask, Response, jsonify, request, render_template_string
from flask_cors import CORS
import time
import os

app = Flask(__name__)
CORS(app)
LOG_FILE = 'auditoriaEC.log'

def tail_lines(path: str, count: int = 50):
    """Return the last `count` lines from the log file."""
    if not os.path.exists(path):
        return []
    with open(path, 'r') as f:
        lines = f.readlines()
    return lines[-count:]

LOG_PAGE_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Audit Logs</title>
    <style>
        body { font-family: Arial, sans-serif; padding: 20px; }
        #audit-logs {
            max-height: 300px;
            overflow-y: auto;
            white-space: pre-wrap;
            background-color: #fafafa;
            border: 1px solid #d0d0d0;
            border-radius: 5px;
            padding: 10px;
        }
        .log-entry {
            padding: 2px 4px;
            margin-bottom: 2px;
            border-bottom: 1px solid #d0d0d0;
            font-family: monospace;
        }
        .log-entry.info { color: #2e7d32; }
        .log-entry.error { color: #c62828; }
        .log-entry.warning { color: #f9a825; }
    </style>
</head>
<body>
    <h1>Audit Logs</h1>
    <div id="audit-logs">
        {% for line in logs %}
        <div class="log-entry {% if 'ERROR' in line %}error{% elif 'WARNING' in line %}warning{% else %}info{% endif %}">{{ line }}</div>
        {% endfor %}
    </div>
    <script>
        const container = document.getElementById('audit-logs');
        function addLogLine(line) {
            const div = document.createElement('div');
            div.classList.add('log-entry');
            if (line.includes('ERROR')) {
                div.classList.add('error');
            } else if (line.includes('WARNING')) {
                div.classList.add('warning');
            } else {
                div.classList.add('info');
            }
            div.textContent = line;
            container.prepend(div);
            container.scrollTop = 0;
        }

        async function fetchLogs() {
            try {
                const response = await fetch('/logs?lines=50', {headers: {Accept: 'application/json'}});
                const data = await response.json();
                container.innerHTML = '';
                data.logs.split('\n').forEach(l => { if (l.trim()) addLogLine(l); });
            } catch (err) {
                console.error('Error fetching logs', err);
            }
        }

        const source = new EventSource('/logs/stream');
        source.onmessage = (e) => addLogLine(e.data);
        fetchLogs();
    </script>
</body>
</html>
'''

@app.route('/logs', methods=['GET'])
def get_logs():
    accept = request.headers.get('Accept', '')
    line_count = request.args.get('lines', default=50, type=int)
    log_lines = tail_lines(LOG_FILE, line_count)
    if 'text/html' in accept:
        return render_template_string(LOG_PAGE_TEMPLATE, logs=log_lines)
    return jsonify({'logs': ''.join(log_lines)})

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
    return Response(generate(), mimetype='text/event-stream', headers={'Cache-Control': 'no-cache'})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5003)