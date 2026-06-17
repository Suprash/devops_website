# Student Authentication Service — Monitoring & Observability Demo

A microservice-based authentication system instrumented with **Prometheus**
metrics, visualized in **Grafana**, fully containerized with **Docker** and
**Docker Compose**. Built to demonstrate microservice architecture,
observability practices, and containerization in a single, runnable project.

---

## 1. Quick Start

```bash
# Build and start everything (app + prometheus + grafana)
docker-compose up --build

# App:        http://localhost:5000
# Prometheus: http://localhost:9090
# Grafana:    http://localhost:3000   (login: admin / admin)
```

The Grafana dashboard **"Authentication Service Monitoring"** is
auto-provisioned — you don't need to manually add a data source or import
anything. It will already be sitting in the Dashboards list when you log in.

### Generate some traffic to see the dashboard populate

```bash
# Register a user
curl -X POST http://localhost:5000/register \
  -H "Content-Type: application/json" \
  -d '{"username": "alice", "password": "wonderland"}'

# Successful login
curl -X POST http://localhost:5000/login \
  -H "Content-Type: application/json" \
  -d '{"username": "alice", "password": "wonderland"}'

# Failed login (wrong password) — run a few times to see lockout logging
curl -X POST http://localhost:5000/login \
  -H "Content-Type: application/json" \
  -d '{"username": "alice", "password": "wrong"}'

# Session check (use the session_token returned by a successful login)
curl http://localhost:5000/session -H "Authorization: Bearer <token>"

# Health check
curl http://localhost:5000/health

# Raw Prometheus metrics
curl http://localhost:5000/metrics
```

A quick load-test loop, if you want livelier graphs:
```bash
for i in $(seq 1 50); do
  curl -s -X POST http://localhost:5000/login \
    -H "Content-Type: application/json" \
    -d '{"username":"alice","password":"wonderland"}' > /dev/null
done
```

---

## 2. Project Structure

```
.
├── app.py                          # Flask API: auth logic + metrics + logging
├── requirements.txt                # Python dependencies
├── Dockerfile                      # Builds the Flask app image
├── docker-compose.yml              # Orchestrates app + prometheus + grafana
├── prometheus.yml                  # Prometheus scrape configuration
├── grafana/
│   └── provisioning/
│       ├── datasources/
│       │   └── datasource.yml      # Auto-registers Prometheus as a data source
│       └── dashboards/
│           ├── dashboard.yml       # Tells Grafana where to find dashboard JSON
│           └── json/
│               └── auth-dashboard.json   # The pre-built dashboard (4+ panels)
└── README.md                       # This file
```

---

## 3. API Reference

| Endpoint     | Method | Description                                  |
|--------------|--------|-----------------------------------------------|
| `/register`  | POST   | Create a new user. Body: `{username, password}` |
| `/login`     | POST   | Authenticate a user, returns a session token |
| `/session`   | GET    | Check if a session token is logged in (`Authorization: Bearer <token>`) |
| `/logout`    | POST   | Invalidate a session token |
| `/health`    | GET    | Liveness probe for Docker/Prometheus |
| `/metrics`   | GET    | Prometheus-formatted metrics |

Users and sessions are stored **in-memory** (a Python dict) — by design,
per the assignment scope. Restarting the app clears all data.

---

## 4. Metrics Tracked

| Metric                          | Type      | Purpose                                  |
|----------------------------------|-----------|-------------------------------------------|
| `http_requests_total`           | Counter   | Total requests, labeled by method/endpoint/status |
| `login_attempts_total`          | Counter   | Every login attempt (success or fail)    |
| `login_success_total`           | Counter   | Successful logins only                   |
| `login_failure_total`           | Counter   | Failed logins only                       |
| `http_request_duration_seconds` | Histogram | Response time, used for latency panels   |
| `active_sessions`               | Gauge     | Number of currently logged-in users      |
| `registrations_total`           | Counter   | Total successful registrations           |

---

## 5. Logging

Logs are written to both stdout (visible via `docker logs auth-app`) and a
local `app.log` file inside the container. Three categories are covered:

- **Normal logs:** user registered, login success
- **Error logs:** invalid user, wrong password
- **Security-style logs:** repeated failed attempts and account lockouts
  (e.g. `User 'admin' locked after 3 attempts`)

View live logs:
```bash
docker logs -f auth-app
```

---

## 6. Architecture / System Flow

```
 ┌──────────┐      HTTP       ┌──────────────┐
 │ Student  │ ───────────────▶│  Flask API   │
 │ (client) │                 │  (app.py)    │
 └──────────┘                 └──────┬───────┘
                                      │ updates counters/gauges
                                      ▼
                              ┌───────────────┐
                              │ /metrics      │ (in-process Prometheus client)
                              └──────┬────────┘
                                     │ scraped every 5s
                                     ▼
                              ┌───────────────┐
                              │  Prometheus   │  (stores time-series data)
                              └──────┬────────┘
                                     │ queried via PromQL
                                     ▼
                              ┌───────────────┐
                              │   Grafana     │  (dashboards/visualization)
                              └───────────────┘
```

1. A student sends a request (register/login/session check) to the Flask API.
2. Flask processes the request, updates in-memory data, and increments the
   relevant Prometheus metric (counter/histogram/gauge).
3. Prometheus scrapes the `/metrics` endpoint on the `app` container every
   5 seconds (configured in `prometheus.yml`) and stores the values as
   time-series data.
4. Grafana queries Prometheus using PromQL and renders the pre-built
   dashboard panels in near real time.

All three services run in separate Docker containers, connected on a shared
`monitoring` bridge network, demonstrating a basic microservice topology.

---

## 7. Report Sections (for your CLO submission)

### 5.1 Description
This project implements a lightweight student authentication microservice
exposed via a REST API. Alongside core auth functionality (register, login,
session check), the system is fully instrumented for observability:
Prometheus collects real-time metrics from the API, and Grafana visualizes
that data on a live dashboard. The entire stack is containerized so it can
be deployed with a single `docker-compose up` command.

### 5.2 Objective
- Build a working authentication system (register / login / session check)
- Monitor login behavior and system performance using Prometheus metrics
- Visualize traffic, latency, and login outcomes using Grafana dashboards
- Demonstrate containerized microservice deployment with Docker Compose

### 5.3 Tools
- **Flask** — REST API framework for the authentication service
- **prometheus-client** — Python library exposing metrics in Prometheus format
- **Prometheus** — Metrics collection and time-series storage
- **Grafana** — Dashboarding and visualization
- **Docker / Docker Compose** — Containerization and service orchestration

### 5.4 Time Estimate (suggested breakdown)
| Phase                                    | Estimated time |
|-------------------------------------------|----------------|
| Flask API design (register/login/session) | 2–3 hours      |
| Prometheus metrics instrumentation        | 1–2 hours      |
| Logging implementation                    | 1 hour         |
| Dockerfile + docker-compose setup         | 1–2 hours      |
| Prometheus configuration                  | 30 minutes     |
| Grafana dashboard design                  | 2 hours        |
| Testing + traffic generation              | 1 hour         |
| Report writing                            | 2 hours        |

### 5.5 Deliverables
- Working Flask authentication API (`app.py`)
- Prometheus metrics endpoint (`/metrics`) with 6+ tracked metrics
- Grafana dashboard with 4 required panels (login attempts over time,
  success vs failed logins, request rate, API latency) plus 3 bonus stat panels
- Docker Compose setup running all 3 services together
- Structured logs covering normal, error, and security-style events

### 5.6 Steps and Explanation
1. **Design the API** — defined the 4 core endpoints plus logout as a bonus,
   using an in-memory dict instead of a database to keep scope manageable.
2. **Add metrics** — wrapped key operations (requests, logins, registrations)
   with Prometheus Counters/Gauges/Histograms, exposed at `/metrics`.
3. **Add logging** — used Python's `logging` module to record info/error/
   warning-level events to both console and file.
4. **Containerize the app** — wrote a `Dockerfile` using `python:3.12-slim`
   and `gunicorn` for a production-style server process.
5. **Orchestrate with Compose** — defined `app`, `prometheus`, and `grafana`
   services on a shared bridge network, with named volumes for persistence.
6. **Configure Prometheus** — pointed its scrape config at `app:5000/metrics`
   with a 5-second scrape interval.
7. **Build the Grafana dashboard** — provisioned a data source and dashboard
   JSON automatically so the grader doesn't need to set anything up by hand.

---

## 8. Why This Meets the Grading Criteria

| Requirement                  | How it's satisfied                                        |
|-------------------------------|-------------------------------------------------------------|
| Microservice concept          | Standalone Flask API with clearly scoped responsibilities  |
| Monitoring system             | Prometheus scraping 6+ custom metrics every 5 seconds      |
| Visualization                 | Grafana dashboard with 7 panels, auto-provisioned           |
| Containerization               | Dockerfile + docker-compose.yml running all 3 services      |
| Real-world scenario            | Authentication flow with register/login/session/lockout     |
| Metrics + logs (observability) | Counters, Gauge, Histogram + categorized logging            |

---

## 9. Troubleshooting

- **Grafana shows "No Data":** generate some traffic first (see Quick Start)
  and make sure the time range in the top-right of Grafana is set to
  something recent like "Last 15 minutes".
- **Prometheus target shows as "down":** check `docker-compose ps` to make
  sure the `app` container is healthy, and confirm `prometheus.yml` uses
  `app:5000` (the Compose service name), not `localhost:5000`.
- **Port already in use:** change the host-side port mapping in
  `docker-compose.yml` (e.g. `"5001:5000"`) if 5000/9090/3000 are taken on
  your machine.