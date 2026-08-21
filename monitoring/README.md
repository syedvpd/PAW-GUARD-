# 📊 PawGuard Monitoring Stack (Prometheus & Grafana)

This directory contains the production-ready monitoring setup for the PawGuard Backend.

---

## 🚀 Quick Start (1 Command Setup)

To launch Prometheus & Grafana locally or on your monitoring server:

```bash
docker-compose -f monitoring/docker-compose.monitoring.yml up -d
```

---

## 🌐 Endpoints & Dashboards

1. **Grafana Dashboard**:
   - URL: `http://localhost:3000`
   - Default User: `admin`
   - Default Password: `admin`
   - Pre-configured Dashboard: **PawGuard Production Overview**

2. **Prometheus Metrics Engine**:
   - URL: `http://localhost:9090`
   - Scrape Target: `https://pawguard-backend-mqri.onrender.com/metrics`

---

## 📌 Tracked Production Metrics

- **Requests Per Second (RPS)**: `sum(rate(http_requests_total[1m]))`
- **HTTP Error Rate**: `sum(rate(http_requests_total{status=~"5.."}[1m]))`
- **Average API Response Time (ms)**: `rate(http_request_duration_ms_sum[1m]) / rate(http_request_duration_ms_count[1m])`
- **Successful & Failed Logins**: `sum(rate(auth_login_attempts_total[1m]))`
- **Real-Time Push Dispatches**: `sum(rate(fcm_push_dispatches_total[1m]))`
