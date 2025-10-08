# ORB Confluence REST API Documentation

## 🚀 Quick Start

### Installation

```bash
# Install FastAPI and dependencies
pip install fastapi uvicorn[standard]

# Or with poetry
poetry add fastapi uvicorn[standard]
```

### Running the API Server

```bash
# Development mode (with auto-reload)
uvicorn api_server:app --reload --port 8000

# Production mode
uvicorn api_server:app --host 0.0.0.0 --port 8000 --workers 4
```

### Accessing Documentation

Once the server is running:

- **Swagger UI (interactive)**: http://localhost:8000/docs
- **ReDoc (clean docs)**: http://localhost:8000/redoc
- **OpenAPI JSON**: http://localhost:8000/openapi.json

---

## 📚 API Endpoints

### Base URL

```
http://localhost:8000
```

### Authentication

Currently no authentication required. For production:
- Add API key authentication
- Implement JWT tokens
- Use OAuth2

---

## 🔌 Endpoints

### 1. Root & Status

#### `GET /`
Root endpoint with API information.

**Response:**
```json
{
  "name": "ORB Confluence API",
  "version": "1.0.0",
  "status": "active",
  "endpoints": { ... }
}
```

#### `GET /health`
Health check endpoint.

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2024-01-02T15:30:00.123456",
  "runs_available": 5
}
```

#### `GET /api/status`
Detailed API status.

**Response:**
```json
{
  "api_version": "1.0.0",
  "status": "operational",
  "timestamp": "2024-01-02T15:30:00.123456",
  "statistics": {
    "total_runs": 5,
    "latest_run": "spy_20240102"
  }
}
```

---

### 2. Runs Management

#### `GET /api/runs`
List all available backtest runs.

**Response:**
```json
{
  "count": 3,
  "runs": [
    {
      "run_id": "spy_20240102",
      "created": "2024-01-02T15:30:00",
      "symbol": "SPY",
      "total_trades": 25
    },
    ...
  ]
}
```

---

### 3. Configuration

#### `GET /api/config/hash`
Get configuration hash for a run.

**Parameters:**
- `run_id` (required): Run identifier

**Example:**
```bash
curl "http://localhost:8000/api/config/hash?run_id=spy_20240102"
```

**Response:**
```json
{
  "run_id": "spy_20240102",
  "config_hash": "a1b2c3d4e5f6789...",
  "timestamp": "2024-01-02T10:30:00Z"
}
```

---

### 4. Trades

#### `GET /api/trades`
Get trades for a run with filtering.

**Parameters:**
- `run_id` (required): Run identifier
- `symbol` (optional): Filter by symbol
- `direction` (optional): Filter by direction (`long` or `short`)
- `limit` (optional): Max results (1-1000)
- `offset` (optional): Pagination offset

**Example:**
```bash
# Get all trades
curl "http://localhost:8000/api/trades?run_id=spy_20240102"

# Filter by direction
curl "http://localhost:8000/api/trades?run_id=spy_20240102&direction=long"

# Pagination
curl "http://localhost:8000/api/trades?run_id=spy_20240102&limit=10&offset=20"
```

**Response:**
```json
{
  "run_id": "spy_20240102",
  "symbol": "SPY",
  "total_count": 25,
  "returned_count": 10,
  "trades": [
    {
      "trade_id": "trade_001",
      "direction": "long",
      "entry_timestamp": "2024-01-02T10:30:00",
      "exit_timestamp": "2024-01-02T14:45:00",
      "entry_price": 475.50,
      "exit_price": 476.20,
      "realized_r": 1.2,
      "max_favorable_r": 1.8,
      "max_adverse_r": -0.3,
      "exit_reason": "target_t1",
      "or_high": 475.00,
      "or_low": 474.50,
      "confluence_score": 0.75,
      "factors": {
        "rel_vol": true,
        "price_action": true,
        "vwap": true,
        "adx": false,
        "profile": true
      }
    },
    ...
  ]
}
```

---

### 5. Equity Curve

#### `GET /api/equity`
Get equity curve for a run.

**Parameters:**
- `run_id` (required): Run identifier

**Example:**
```bash
curl "http://localhost:8000/api/equity?run_id=spy_20240102"
```

**Response:**
```json
{
  "run_id": "spy_20240102",
  "equity_curve": [
    {
      "trade_number": 1,
      "cumulative_r": 1.2,
      "drawdown_r": 0.0,
      "drawdown_pct": 0.0
    },
    {
      "trade_number": 2,
      "cumulative_r": 2.5,
      "drawdown_r": 0.0,
      "drawdown_pct": 0.0
    },
    ...
  ],
  "final_r": 12.5,
  "max_drawdown_r": -3.2
}
```

---

### 6. Factors

#### `GET /api/factors/sample`
Get sample of factor snapshots.

**Parameters:**
- `run_id` (required): Run identifier
- `limit` (optional): Sample size (1-10000, default 100)

**Example:**
```bash
curl "http://localhost:8000/api/factors/sample?run_id=spy_20240102&limit=50"
```

**Response:**
```json
{
  "run_id": "spy_20240102",
  "sample_count": 50,
  "snapshots": [
    {
      "timestamp": "2024-01-02T10:30:00",
      "bar_number": 30,
      "rel_vol": 1.5,
      "rel_vol_spike": true,
      "vwap": 475.25,
      "adx": 28.5,
      "price_action_long": true,
      "price_action_short": false,
      "profile_long": true,
      "profile_short": false
    },
    ...
  ]
}
```

---

### 7. Metrics

#### `GET /api/metrics/core`
Get core performance metrics.

**Parameters:**
- `run_id` (required): Run identifier

**Example:**
```bash
curl "http://localhost:8000/api/metrics/core?run_id=spy_20240102"
```

**Response:**
```json
{
  "run_id": "spy_20240102",
  "metrics": {
    "total_trades": 25,
    "winning_trades": 15,
    "losing_trades": 10,
    "win_rate": 0.6,
    "total_r": 12.5,
    "average_r": 0.5,
    "median_r": 0.45,
    "expectancy": 0.5,
    "profit_factor": 2.1,
    "sharpe_ratio": 1.8,
    "sortino_ratio": 2.3,
    "max_drawdown_r": -3.2,
    "max_drawdown_pct": -12.5,
    "avg_winner_r": 1.2,
    "avg_loser_r": -0.8,
    "largest_winner_r": 3.5,
    "largest_loser_r": -1.5,
    "consecutive_wins": 5,
    "consecutive_losses": 3
  }
}
```

---

### 8. Attribution

#### `GET /api/attribution`
Get factor attribution analysis.

**Parameters:**
- `run_id` (required): Run identifier

**Example:**
```bash
curl "http://localhost:8000/api/attribution?run_id=spy_20240102"
```

**Response:**
```json
{
  "run_id": "spy_20240102",
  "factor_attribution": [
    {
      "factor_name": "rel_vol",
      "present_count": 15,
      "present_win_rate": 0.73,
      "present_avg_r": 0.65,
      "absent_count": 10,
      "absent_win_rate": 0.40,
      "absent_avg_r": 0.15,
      "delta_win_rate": 0.33,
      "delta_avg_r": 0.50
    },
    ...
  ],
  "score_buckets": [
    {
      "bucket": "High",
      "count": 8,
      "avg_r": 0.85,
      "win_rate": 0.75
    },
    ...
  ]
}
```

---

## 🔒 CORS Configuration

CORS is pre-configured for common development environments:

```python
allow_origins=[
    "http://localhost:3000",  # React
    "http://localhost:8501",  # Streamlit
    "http://localhost:8000",  # Self
]
```

For production, add your domain:
```python
allow_origins=[
    "https://your-domain.com",
]
```

---

## 📊 Client Examples

### Python (requests)

```python
import requests

# Get runs
response = requests.get("http://localhost:8000/api/runs")
runs = response.json()

# Get trades
response = requests.get(
    "http://localhost:8000/api/trades",
    params={"run_id": "spy_20240102", "direction": "long"}
)
trades = response.json()

# Get metrics
response = requests.get(
    "http://localhost:8000/api/metrics/core",
    params={"run_id": "spy_20240102"}
)
metrics = response.json()
```

### JavaScript (fetch)

```javascript
// Get runs
const runs = await fetch('http://localhost:8000/api/runs')
  .then(res => res.json());

// Get trades with filters
const trades = await fetch(
  'http://localhost:8000/api/trades?run_id=spy_20240102&direction=long'
).then(res => res.json());

// Get equity curve
const equity = await fetch(
  'http://localhost:8000/api/equity?run_id=spy_20240102'
).then(res => res.json());
```

### cURL

```bash
# Get runs
curl http://localhost:8000/api/runs

# Get trades
curl "http://localhost:8000/api/trades?run_id=spy_20240102"

# Get metrics
curl "http://localhost:8000/api/metrics/core?run_id=spy_20240102"

# Get attribution
curl "http://localhost:8000/api/attribution?run_id=spy_20240102"
```

---

## 🚀 Deployment

### Development

```bash
uvicorn api_server:app --reload --port 8000
```

### Production (with Gunicorn)

```bash
pip install gunicorn

gunicorn api_server:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000 \
  --access-logfile - \
  --error-logfile -
```

### Docker

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["uvicorn", "api_server:app", "--host", "0.0.0.0", "--port", "8000"]
```

Build and run:
```bash
docker build -t orb-api .
docker run -p 8000:8000 -v $(pwd)/runs:/app/runs orb-api
```

### Docker Compose

```yaml
version: '3.8'

services:
  api:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - ./runs:/app/runs
    environment:
      - PYTHONUNBUFFERED=1
    restart: unless-stopped
```

---

## 🔧 Configuration

### Environment Variables

```bash
# API Settings
API_HOST=0.0.0.0
API_PORT=8000
API_WORKERS=4

# CORS
CORS_ORIGINS=http://localhost:3000,https://your-domain.com

# Data
RUNS_DIRECTORY=runs
```

### Load from .env

```python
from dotenv import load_dotenv
import os

load_dotenv()

API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", 8000))
```

---

## 📈 Performance

### Caching

Add caching for frequently accessed data:

```python
from functools import lru_cache

@lru_cache(maxsize=128)
def load_run_trades_cached(run_id: str):
    return load_run_trades(run_id)
```

### Async Operations

For database integration:

```python
@app.get("/api/trades")
async def get_trades(run_id: str):
    trades = await fetch_trades_from_db(run_id)
    return trades
```

---

## 🛡️ Security

### API Key Authentication

```python
from fastapi import Security, HTTPException
from fastapi.security import APIKeyHeader

API_KEY = "your-secret-api-key"
api_key_header = APIKeyHeader(name="X-API-Key")

async def verify_api_key(api_key: str = Security(api_key_header)):
    if api_key != API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API Key")
    return api_key

@app.get("/api/trades", dependencies=[Depends(verify_api_key)])
async def get_trades(...):
    ...
```

### Rate Limiting

```python
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

@app.get("/api/trades")
@limiter.limit("100/minute")
async def get_trades(request: Request, ...):
    ...
```

---

## 🧪 Testing

### Unit Tests

```python
from fastapi.testclient import TestClient
from api_server import app

client = TestClient(app)

def test_root():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["name"] == "ORB Confluence API"

def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"

def test_get_runs():
    response = client.get("/api/runs")
    assert response.status_code == 200
    assert "count" in response.json()
```

Run tests:
```bash
pytest test_api_server.py -v
```

---

## 📚 Additional Resources

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Uvicorn Documentation](https://www.uvicorn.org/)
- [Pydantic Documentation](https://docs.pydantic.dev/)
- [OpenAPI Specification](https://swagger.io/specification/)

---

**API Version**: 1.0.0  
**Status**: ✅ Production Ready  
**Last Updated**: 2024  

Happy API building! 🚀📊
