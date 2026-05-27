#!/bin/bash

echo "🚀 AlphaPulse Dual-Process Engine Initializing..."

# 1. Start the Async Event Engine in the background
# Logs will stream directly to Railway's console alongside Streamlit
python async_executor.py &
BOT_PID=$!
echo "✅ Async Executor started in background (PID: $BOT_PID)"

# 2. Start Streamlit in the foreground using 'exec'
# 'exec' ensures Streamlit receives termination signals properly from Railway
echo "🌐 Booting Streamlit Dashboard on port $PORT..."
exec streamlit run dashboard.py --server.port=$PORT --server.address=0.0.0.0
