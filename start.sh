#!/bin/bash
# Start the bot in background
python main.py &
BOT_PID=$!

# Start the dashboard in foreground (Railway expects this)
streamlit run dashboard.py --server.port=$PORT --server.headless=true --server.enableCORS=false --server.enableXsrfProtection=false

# If dashboard exits, kill bot too
kill $BOT_PID 2>/dev/null
wait
