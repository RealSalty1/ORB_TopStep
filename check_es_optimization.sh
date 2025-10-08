#!/bin/bash
# Quick script to check ES optimization progress

echo "=========================================="
echo "ES OPTIMIZATION PROGRESS"
echo "=========================================="
echo ""

# Check if still running
if pgrep -f "optimize_es_only.py" > /dev/null; then
    echo "✅ Status: RUNNING"
    
    # Count completed trials
    COMPLETED=$(grep -c "Trial [0-9]*:" optimization_es.log 2>/dev/null || echo "0")
    echo "📊 Trials completed: $COMPLETED / 20"
    
    # Calculate progress
    PERCENT=$((COMPLETED * 100 / 20))
    echo "📈 Progress: $PERCENT%"
    
    # Estimate time remaining
    ELAPSED_MIN=$(ps -o etime= -p $(pgrep -f "optimize_es_only.py") | awk -F: '{print ($1 * 60) + $2}')
    if [ "$COMPLETED" -gt 0 ]; then
        AVG_PER_TRIAL=$((ELAPSED_MIN / COMPLETED))
        REMAINING=$((AVG_PER_TRIAL * (20 - COMPLETED)))
        echo "⏱️  Est. time remaining: ~$((REMAINING / 60)) minutes"
    fi
    
    echo ""
    echo "Last 3 completed trials:"
    tail -100 optimization_es.log | grep "Trial [0-9]*:" | tail -3
    
else
    echo "✅ Status: COMPLETE!"
    echo ""
    echo "📊 Final Results:"
    tail -50 optimization_es.log | grep -E "Best Expectancy|Best Parameters|R:R|Win Rate" | head -10
fi

echo ""
echo "=========================================="
