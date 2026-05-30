#!/bin/bash
echo "🚀 AlphaPulse Dual-Process Engine Initializing..."

# 🚨 FIX: Set default port if $PORT is empty (Hugging Face Spaces / Railway compatibility)
PORT=${PORT:-7860}
echo "📡 Using port: $PORT"

# 1. Start the Async Event Engine in the background
python async_executor.py &
BOT_PID=$!
echo "✅ Async Executor started in background (PID: $BOT_PID)"

# 2. Start Streamlit in the foreground using 'exec'
echo "🌐 Booting Streamlit Dashboard on port $PORT..."
exec streamlit run dashboard.py --server.port=$PORT --server.address=0.0.0.0 --server.headless=true --server.enableCORS=false --server.enableXsrfProtection=false
