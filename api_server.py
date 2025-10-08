"""FastAPI REST API for ORB Confluence Strategy.

Provides programmatic access to backtest results, metrics, and configuration.

Run with:
    uvicorn api_server:app --reload --port 8000

API docs available at:
    http://localhost:8000/docs (Swagger UI)
    http://localhost:8000/redoc (ReDoc)
"""

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import pandas as pd
import json

# ============================================================================
# API Models (Request/Response Schemas)
# ============================================================================


class TradeDirection(str, Enum):
    """Trade direction enum."""
    LONG = "long"
    SHORT = "short"


class ExitReason(str, Enum):
    """Trade exit reason enum."""
    STOP = "stop"
    TARGET_T1 = "target_t1"
    TARGET_T2 = "target_t2"
    TARGET_RUNNER = "target_runner"
    TIME_CUTOFF = "time_cutoff"
    END_OF_DAY = "end_of_day"


class ConfigHashResponse(BaseModel):
    """Response model for config hash endpoint."""
    run_id: str
    config_hash: str
    timestamp: Optional[str] = None
    
    class Config:
        schema_extra = {
            "example": {
                "run_id": "spy_20240102",
                "config_hash": "a1b2c3d4e5f6...",
                "timestamp": "2024-01-02T10:30:00Z"
            }
        }


class TradeResponse(BaseModel):
    """Response model for individual trade."""
    trade_id: str
    direction: TradeDirection
    entry_timestamp: str
    exit_timestamp: Optional[str] = None
    entry_price: float
    exit_price: Optional[float] = None
    realized_r: Optional[float] = None
    max_favorable_r: Optional[float] = None
    max_adverse_r: Optional[float] = None
    exit_reason: Optional[ExitReason] = None
    or_high: Optional[float] = None
    or_low: Optional[float] = None
    confluence_score: Optional[float] = None
    factors: Optional[Dict[str, bool]] = None
    
    class Config:
        schema_extra = {
            "example": {
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
                    "rel_vol": True,
                    "price_action": True,
                    "vwap": True,
                    "adx": False,
                    "profile": True
                }
            }
        }


class TradesListResponse(BaseModel):
    """Response model for trades list."""
    run_id: str
    symbol: Optional[str] = None
    total_count: int
    returned_count: int
    trades: List[TradeResponse]
    
    class Config:
        schema_extra = {
            "example": {
                "run_id": "spy_20240102",
                "symbol": "SPY",
                "total_count": 25,
                "returned_count": 10,
                "trades": []
            }
        }


class EquityPoint(BaseModel):
    """Single point on equity curve."""
    trade_number: int
    cumulative_r: float
    drawdown_r: float
    drawdown_pct: Optional[float] = None
    
    class Config:
        schema_extra = {
            "example": {
                "trade_number": 10,
                "cumulative_r": 5.2,
                "drawdown_r": -1.1,
                "drawdown_pct": -4.5
            }
        }


class EquityCurveResponse(BaseModel):
    """Response model for equity curve."""
    run_id: str
    equity_curve: List[EquityPoint]
    final_r: float
    max_drawdown_r: float
    
    class Config:
        schema_extra = {
            "example": {
                "run_id": "spy_20240102",
                "equity_curve": [],
                "final_r": 12.5,
                "max_drawdown_r": -3.2
            }
        }


class FactorSnapshot(BaseModel):
    """Factor values at a point in time."""
    timestamp: str
    bar_number: int
    rel_vol: Optional[float] = None
    rel_vol_spike: Optional[bool] = None
    vwap: Optional[float] = None
    adx: Optional[float] = None
    price_action_long: Optional[bool] = None
    price_action_short: Optional[bool] = None
    profile_long: Optional[bool] = None
    profile_short: Optional[bool] = None
    
    class Config:
        schema_extra = {
            "example": {
                "timestamp": "2024-01-02T10:30:00",
                "bar_number": 30,
                "rel_vol": 1.5,
                "rel_vol_spike": True,
                "vwap": 475.25,
                "adx": 28.5,
                "price_action_long": True,
                "price_action_short": False
            }
        }


class FactorSampleResponse(BaseModel):
    """Response model for factor samples."""
    run_id: str
    sample_count: int
    snapshots: List[FactorSnapshot]
    
    class Config:
        schema_extra = {
            "example": {
                "run_id": "spy_20240102",
                "sample_count": 50,
                "snapshots": []
            }
        }


class CoreMetrics(BaseModel):
    """Core performance metrics."""
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float = Field(..., ge=0.0, le=1.0)
    total_r: float
    average_r: float
    median_r: float
    expectancy: float
    profit_factor: Optional[float] = None
    sharpe_ratio: Optional[float] = None
    sortino_ratio: Optional[float] = None
    max_drawdown_r: float
    max_drawdown_pct: Optional[float] = None
    avg_winner_r: float
    avg_loser_r: float
    largest_winner_r: float
    largest_loser_r: float
    consecutive_wins: int
    consecutive_losses: int
    
    class Config:
        schema_extra = {
            "example": {
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


class MetricsResponse(BaseModel):
    """Response model for metrics endpoint."""
    run_id: str
    metrics: CoreMetrics
    
    class Config:
        schema_extra = {
            "example": {
                "run_id": "spy_20240102",
                "metrics": {}
            }
        }


class FactorAttribution(BaseModel):
    """Attribution for a single factor."""
    factor_name: str
    present_count: int
    present_win_rate: float
    present_avg_r: float
    absent_count: int
    absent_win_rate: float
    absent_avg_r: float
    delta_win_rate: float
    delta_avg_r: float
    
    class Config:
        schema_extra = {
            "example": {
                "factor_name": "rel_vol",
                "present_count": 15,
                "present_win_rate": 0.73,
                "present_avg_r": 0.65,
                "absent_count": 10,
                "absent_win_rate": 0.40,
                "absent_avg_r": 0.15,
                "delta_win_rate": 0.33,
                "delta_avg_r": 0.50
            }
        }


class ScoreBucket(BaseModel):
    """Performance for a score bucket."""
    bucket: str
    count: int
    avg_r: float
    win_rate: float
    
    class Config:
        schema_extra = {
            "example": {
                "bucket": "High",
                "count": 8,
                "avg_r": 0.85,
                "win_rate": 0.75
            }
        }


class AttributionResponse(BaseModel):
    """Response model for attribution analysis."""
    run_id: str
    factor_attribution: List[FactorAttribution]
    score_buckets: List[ScoreBucket]
    
    class Config:
        schema_extra = {
            "example": {
                "run_id": "spy_20240102",
                "factor_attribution": [],
                "score_buckets": []
            }
        }


class RunInfo(BaseModel):
    """Information about a single run."""
    run_id: str
    created: Optional[str] = None
    symbol: Optional[str] = None
    total_trades: Optional[int] = None
    
    class Config:
        schema_extra = {
            "example": {
                "run_id": "spy_20240102",
                "created": "2024-01-02T15:30:00",
                "symbol": "SPY",
                "total_trades": 25
            }
        }


class RunsListResponse(BaseModel):
    """Response model for runs list."""
    count: int
    runs: List[RunInfo]


class ErrorResponse(BaseModel):
    """Error response model."""
    error: str
    detail: Optional[str] = None
    
    class Config:
        schema_extra = {
            "example": {
                "error": "Run not found",
                "detail": "Run ID 'invalid_run' does not exist"
            }
        }


# ============================================================================
# FastAPI Application
# ============================================================================

app = FastAPI(
    title="ORB Confluence API",
    description="REST API for Opening Range Breakout strategy backtesting platform",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS Middleware Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",  # React dev server
        "http://localhost:8501",  # Streamlit
        "http://localhost:8000",  # Self
        # Add production origins here:
        # "https://your-production-domain.com",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)


# ============================================================================
# Helper Functions
# ============================================================================


def get_runs_directory() -> Path:
    """Get the runs directory path."""
    return Path("runs")


def list_available_runs() -> List[str]:
    """List all available run directories."""
    runs_dir = get_runs_directory()
    if not runs_dir.exists():
        return []
    return sorted([d.name for d in runs_dir.iterdir() if d.is_dir()], reverse=True)


def load_run_trades(run_id: str) -> Optional[pd.DataFrame]:
    """Load trades DataFrame for a run."""
    run_dir = get_runs_directory() / run_id
    
    # Try parquet first
    trades_path = run_dir / "trades.parquet"
    if trades_path.exists():
        return pd.read_parquet(trades_path)
    
    # Fallback to CSV
    trades_csv = run_dir / "trades.csv"
    if trades_csv.exists():
        return pd.read_csv(trades_csv)
    
    return None


def load_run_equity(run_id: str) -> Optional[pd.DataFrame]:
    """Load equity curve DataFrame for a run."""
    run_dir = get_runs_directory() / run_id
    
    # Try parquet first
    equity_path = run_dir / "equity_curve.parquet"
    if equity_path.exists():
        return pd.read_parquet(equity_path)
    
    # Fallback to CSV
    equity_csv = run_dir / "equity_curve.csv"
    if equity_csv.exists():
        return pd.read_csv(equity_csv)
    
    return None


def load_run_factors(run_id: str) -> Optional[pd.DataFrame]:
    """Load factor snapshots DataFrame for a run."""
    run_dir = get_runs_directory() / run_id
    
    factors_path = run_dir / "factor_snapshots.parquet"
    if factors_path.exists():
        return pd.read_parquet(factors_path)
    
    return None


def load_run_config(run_id: str) -> Optional[Dict]:
    """Load config JSON for a run."""
    run_dir = get_runs_directory() / run_id
    
    config_path = run_dir / "config.json"
    if config_path.exists():
        with open(config_path) as f:
            return json.load(f)
    
    return None


def load_run_metrics(run_id: str) -> Optional[Dict]:
    """Load metrics JSON for a run."""
    run_dir = get_runs_directory() / run_id
    
    metrics_path = run_dir / "metrics.json"
    if metrics_path.exists():
        with open(metrics_path) as f:
            return json.load(f)
    
    return None


# ============================================================================
# API Endpoints
# ============================================================================


@app.get("/", tags=["root"])
async def root():
    """Root endpoint - API information."""
    return {
        "name": "ORB Confluence API",
        "version": "1.0.0",
        "status": "active",
        "endpoints": {
            "docs": "/docs",
            "redoc": "/redoc",
            "runs": "/api/runs",
            "config": "/api/config/hash?run_id={run_id}",
            "trades": "/api/trades?run_id={run_id}&symbol={symbol}",
            "equity": "/api/equity?run_id={run_id}",
            "factors": "/api/factors/sample?run_id={run_id}&limit={limit}",
            "metrics": "/api/metrics/core?run_id={run_id}",
            "attribution": "/api/attribution?run_id={run_id}",
        }
    }


@app.get("/api/runs", response_model=RunsListResponse, tags=["runs"])
async def get_runs():
    """List all available backtest runs.
    
    Returns:
        List of run IDs with metadata.
    """
    runs = list_available_runs()
    
    run_infos = []
    for run_id in runs:
        info = RunInfo(run_id=run_id)
        
        # Try to load basic metadata
        metrics = load_run_metrics(run_id)
        if metrics:
            info.total_trades = metrics.get('total_trades')
        
        run_infos.append(info)
    
    return RunsListResponse(count=len(run_infos), runs=run_infos)


@app.get("/api/config/hash", response_model=ConfigHashResponse, tags=["config"])
async def get_config_hash(run_id: str = Query(..., description="Run ID")):
    """Get configuration hash for a run.
    
    Args:
        run_id: The run identifier.
        
    Returns:
        Config hash and metadata.
        
    Raises:
        HTTPException: If run not found or config unavailable.
    """
    if run_id not in list_available_runs():
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    
    config = load_run_config(run_id)
    if not config:
        raise HTTPException(status_code=404, detail=f"Config not found for run '{run_id}'")
    
    # Extract or compute hash
    config_hash = config.get('hash', 'N/A')
    timestamp = config.get('timestamp')
    
    return ConfigHashResponse(
        run_id=run_id,
        config_hash=config_hash,
        timestamp=timestamp
    )


@app.get("/api/trades", response_model=TradesListResponse, tags=["trades"])
async def get_trades(
    run_id: str = Query(..., description="Run ID"),
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
    direction: Optional[TradeDirection] = Query(None, description="Filter by direction"),
    limit: Optional[int] = Query(None, ge=1, le=1000, description="Limit results"),
    offset: int = Query(0, ge=0, description="Offset for pagination")
):
    """Get trades for a run with optional filtering.
    
    Args:
        run_id: The run identifier.
        symbol: Optional symbol filter.
        direction: Optional direction filter (long/short).
        limit: Maximum number of trades to return.
        offset: Number of trades to skip.
        
    Returns:
        List of trades matching filters.
        
    Raises:
        HTTPException: If run not found or no trades available.
    """
    if run_id not in list_available_runs():
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    
    trades_df = load_run_trades(run_id)
    if trades_df is None or len(trades_df) == 0:
        raise HTTPException(status_code=404, detail=f"No trades found for run '{run_id}'")
    
    # Apply filters
    filtered_df = trades_df.copy()
    
    if symbol:
        if 'symbol' in filtered_df.columns:
            filtered_df = filtered_df[filtered_df['symbol'] == symbol]
    
    if direction:
        if 'direction' in filtered_df.columns:
            filtered_df = filtered_df[filtered_df['direction'] == direction.value]
    
    total_count = len(filtered_df)
    
    # Apply pagination
    filtered_df = filtered_df.iloc[offset:]
    if limit:
        filtered_df = filtered_df.iloc[:limit]
    
    # Convert to response models
    trades = []
    for _, row in filtered_df.iterrows():
        # Extract factor columns
        factor_cols = [col for col in row.index if col.startswith('factor_')]
        factors = {col.replace('factor_', ''): bool(row[col]) for col in factor_cols} if factor_cols else None
        
        trade = TradeResponse(
            trade_id=str(row.get('trade_id', '')),
            direction=TradeDirection(row['direction']),
            entry_timestamp=str(row['entry_timestamp']),
            exit_timestamp=str(row['exit_timestamp']) if pd.notna(row.get('exit_timestamp')) else None,
            entry_price=float(row['entry_price']),
            exit_price=float(row['exit_price']) if pd.notna(row.get('exit_price')) else None,
            realized_r=float(row['realized_r']) if pd.notna(row.get('realized_r')) else None,
            max_favorable_r=float(row['max_favorable_r']) if pd.notna(row.get('max_favorable_r')) else None,
            max_adverse_r=float(row['max_adverse_r']) if pd.notna(row.get('max_adverse_r')) else None,
            exit_reason=ExitReason(row['exit_reason']) if pd.notna(row.get('exit_reason')) else None,
            or_high=float(row['or_high']) if pd.notna(row.get('or_high')) else None,
            or_low=float(row['or_low']) if pd.notna(row.get('or_low')) else None,
            confluence_score=float(row['confluence_score']) if pd.notna(row.get('confluence_score')) else None,
            factors=factors
        )
        trades.append(trade)
    
    return TradesListResponse(
        run_id=run_id,
        symbol=symbol,
        total_count=total_count,
        returned_count=len(trades),
        trades=trades
    )


@app.get("/api/equity", response_model=EquityCurveResponse, tags=["equity"])
async def get_equity_curve(run_id: str = Query(..., description="Run ID")):
    """Get equity curve for a run.
    
    Args:
        run_id: The run identifier.
        
    Returns:
        Equity curve data points.
        
    Raises:
        HTTPException: If run not found or equity data unavailable.
    """
    if run_id not in list_available_runs():
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    
    equity_df = load_run_equity(run_id)
    if equity_df is None or len(equity_df) == 0:
        raise HTTPException(status_code=404, detail=f"No equity data found for run '{run_id}'")
    
    # Convert to response models
    equity_points = []
    for idx, row in equity_df.iterrows():
        point = EquityPoint(
            trade_number=int(idx) if isinstance(idx, (int, float)) else int(row.get('trade_number', idx)),
            cumulative_r=float(row['cumulative_r']),
            drawdown_r=float(row['drawdown_r']),
            drawdown_pct=float(row['drawdown_pct']) if 'drawdown_pct' in row and pd.notna(row['drawdown_pct']) else None
        )
        equity_points.append(point)
    
    final_r = float(equity_df['cumulative_r'].iloc[-1])
    max_dd = float(equity_df['drawdown_r'].min())
    
    return EquityCurveResponse(
        run_id=run_id,
        equity_curve=equity_points,
        final_r=final_r,
        max_drawdown_r=max_dd
    )


@app.get("/api/factors/sample", response_model=FactorSampleResponse, tags=["factors"])
async def get_factor_sample(
    run_id: str = Query(..., description="Run ID"),
    limit: int = Query(100, ge=1, le=10000, description="Sample size")
):
    """Get sample of factor snapshots for a run.
    
    Args:
        run_id: The run identifier.
        limit: Maximum number of snapshots to return.
        
    Returns:
        Sample of factor values over time.
        
    Raises:
        HTTPException: If run not found or factor data unavailable.
    """
    if run_id not in list_available_runs():
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    
    factors_df = load_run_factors(run_id)
    if factors_df is None or len(factors_df) == 0:
        raise HTTPException(status_code=404, detail=f"No factor data found for run '{run_id}'")
    
    # Sample if needed
    if len(factors_df) > limit:
        factors_df = factors_df.sample(n=limit).sort_index()
    
    # Convert to response models
    snapshots = []
    for idx, row in factors_df.iterrows():
        snapshot = FactorSnapshot(
            timestamp=str(row.get('timestamp', idx)),
            bar_number=int(row.get('bar_number', idx)),
            rel_vol=float(row['rel_vol']) if 'rel_vol' in row and pd.notna(row['rel_vol']) else None,
            rel_vol_spike=bool(row['rel_vol_spike']) if 'rel_vol_spike' in row and pd.notna(row['rel_vol_spike']) else None,
            vwap=float(row['vwap']) if 'vwap' in row and pd.notna(row['vwap']) else None,
            adx=float(row['adx']) if 'adx' in row and pd.notna(row['adx']) else None,
            price_action_long=bool(row['price_action_long']) if 'price_action_long' in row and pd.notna(row['price_action_long']) else None,
            price_action_short=bool(row['price_action_short']) if 'price_action_short' in row and pd.notna(row['price_action_short']) else None,
            profile_long=bool(row['profile_long']) if 'profile_long' in row and pd.notna(row['profile_long']) else None,
            profile_short=bool(row['profile_short']) if 'profile_short' in row and pd.notna(row['profile_short']) else None,
        )
        snapshots.append(snapshot)
    
    return FactorSampleResponse(
        run_id=run_id,
        sample_count=len(snapshots),
        snapshots=snapshots
    )


@app.get("/api/metrics/core", response_model=MetricsResponse, tags=["metrics"])
async def get_core_metrics(run_id: str = Query(..., description="Run ID")):
    """Get core performance metrics for a run.
    
    Args:
        run_id: The run identifier.
        
    Returns:
        Core performance metrics.
        
    Raises:
        HTTPException: If run not found or metrics unavailable.
    """
    if run_id not in list_available_runs():
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    
    metrics_dict = load_run_metrics(run_id)
    if not metrics_dict:
        raise HTTPException(status_code=404, detail=f"No metrics found for run '{run_id}'")
    
    metrics = CoreMetrics(
        total_trades=metrics_dict.get('total_trades', 0),
        winning_trades=metrics_dict.get('winning_trades', 0),
        losing_trades=metrics_dict.get('losing_trades', 0),
        win_rate=metrics_dict.get('win_rate', 0.0),
        total_r=metrics_dict.get('total_r', 0.0),
        average_r=metrics_dict.get('average_r', 0.0),
        median_r=metrics_dict.get('median_r', 0.0),
        expectancy=metrics_dict.get('expectancy', 0.0),
        profit_factor=metrics_dict.get('profit_factor'),
        sharpe_ratio=metrics_dict.get('sharpe_ratio'),
        sortino_ratio=metrics_dict.get('sortino_ratio'),
        max_drawdown_r=metrics_dict.get('max_drawdown_r', 0.0),
        max_drawdown_pct=metrics_dict.get('max_drawdown_pct'),
        avg_winner_r=metrics_dict.get('avg_winner_r', 0.0),
        avg_loser_r=metrics_dict.get('avg_loser_r', 0.0),
        largest_winner_r=metrics_dict.get('largest_winner_r', 0.0),
        largest_loser_r=metrics_dict.get('largest_loser_r', 0.0),
        consecutive_wins=metrics_dict.get('consecutive_wins', 0),
        consecutive_losses=metrics_dict.get('consecutive_losses', 0),
    )
    
    return MetricsResponse(run_id=run_id, metrics=metrics)


@app.get("/api/attribution", response_model=AttributionResponse, tags=["attribution"])
async def get_attribution(run_id: str = Query(..., description="Run ID")):
    """Get factor attribution analysis for a run.
    
    Args:
        run_id: The run identifier.
        
    Returns:
        Factor attribution and score bucket analysis.
        
    Raises:
        HTTPException: If run not found or insufficient data.
    """
    if run_id not in list_available_runs():
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    
    trades_df = load_run_trades(run_id)
    if trades_df is None or len(trades_df) == 0:
        raise HTTPException(status_code=404, detail=f"No trades found for run '{run_id}'")
    
    # Compute factor attribution
    factor_cols = [col for col in trades_df.columns if col.startswith('factor_')]
    
    factor_attributions = []
    for factor_col in factor_cols:
        factor_name = factor_col.replace('factor_', '')
        
        present = trades_df[trades_df[factor_col] == True]
        absent = trades_df[trades_df[factor_col] == False]
        
        if 'realized_r' not in trades_df.columns:
            continue
        
        present_win_rate = (present['realized_r'] > 0).mean() if len(present) > 0 else 0.0
        present_avg_r = present['realized_r'].mean() if len(present) > 0 else 0.0
        
        absent_win_rate = (absent['realized_r'] > 0).mean() if len(absent) > 0 else 0.0
        absent_avg_r = absent['realized_r'].mean() if len(absent) > 0 else 0.0
        
        factor_attributions.append(FactorAttribution(
            factor_name=factor_name,
            present_count=len(present),
            present_win_rate=float(present_win_rate),
            present_avg_r=float(present_avg_r),
            absent_count=len(absent),
            absent_win_rate=float(absent_win_rate),
            absent_avg_r=float(absent_avg_r),
            delta_win_rate=float(present_win_rate - absent_win_rate),
            delta_avg_r=float(present_avg_r - absent_avg_r),
        ))
    
    # Compute score buckets
    score_buckets = []
    if 'confluence_score' in trades_df.columns and 'realized_r' in trades_df.columns:
        trades_df['score_bucket'] = pd.cut(
            trades_df['confluence_score'],
            bins=5,
            labels=['Very Low', 'Low', 'Medium', 'High', 'Very High']
        )
        
        for bucket_name in ['Very Low', 'Low', 'Medium', 'High', 'Very High']:
            bucket_trades = trades_df[trades_df['score_bucket'] == bucket_name]
            if len(bucket_trades) > 0:
                score_buckets.append(ScoreBucket(
                    bucket=bucket_name,
                    count=len(bucket_trades),
                    avg_r=float(bucket_trades['realized_r'].mean()),
                    win_rate=float((bucket_trades['realized_r'] > 0).mean())
                ))
    
    return AttributionResponse(
        run_id=run_id,
        factor_attribution=factor_attributions,
        score_buckets=score_buckets
    )


# ============================================================================
# Health & Status Endpoints
# ============================================================================


@app.get("/health", tags=["status"])
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "runs_available": len(list_available_runs())
    }


@app.get("/api/status", tags=["status"])
async def api_status():
    """Detailed API status."""
    runs = list_available_runs()
    return {
        "api_version": "1.0.0",
        "status": "operational",
        "timestamp": datetime.utcnow().isoformat(),
        "statistics": {
            "total_runs": len(runs),
            "latest_run": runs[0] if runs else None,
        }
    }


# ============================================================================
# Run Server
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "api_server:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
