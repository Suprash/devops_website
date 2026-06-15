from flask import Flask
from prometheus_client import start_http_server, Counter
app = Flask(__name__)
requests = Counter(’http_requests_total’, ’Total HTTP Requests’)
 @app.route(’/’)
def home():
    requests.inc()
    return "Hello, Monitoring!"
if __name__ == ’__main__’:
    start_http_server(8001)
    app.run(host=’0.0.0.0’, port=5000)
