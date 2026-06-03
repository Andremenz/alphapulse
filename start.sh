#!/bin/bash

echo "🚀 Starting AlphaPulse Professional Engine..."

# 1. Start the new Main Engine (WebSocket Listener + Scheduler) in the background
python main.py &

# 2. Start the Streamlit Dashboard
# Note: If your streamlit file is named something other than 'app.py', change it below.
streamlit run app.py --server.port 7860 --server.address 0.0.0.0
