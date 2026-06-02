# Add this at the very top of async_executor.py
import sys
from pathlib import Path

# Ensure fetchers/ is in Python path
app_dir = Path(__file__).parent.resolve()
fetchers_path = app_dir / "fetchers"
if fetchers_path.exists() and str(fetchers_path) not in sys.path:
    sys.path.insert(0, str(fetchers_path))

# Now imports will work
from fetchers.order_flow_scanner import OrderFlowImbalance
from fetchers.circuit_breaker_v2 import CircuitBreakerV2
#!/usr/bin/env python3
"""
AlphaPulse Async Executor - Upgraded Version with Order Flow & Circuit Breaker
"""
import asyncio
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from web3 import Web3

# Import new modules
from fetchers.order_flow_scanner import OrderFlowImbalance
from fetchers.circuit_breaker_v2 import CircuitBreakerV2
from config import settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("AsyncExecutor")

# Initialize Web3
try:
    if settings.quicknode_ws_enabled and settings.base_ws:
        logger.info(f"Connecting to WebSocket: {settings.base_ws[:50]}...")
        w3 = Web3(Web3.WebsocketProvider(settings.base_ws))
    else:
        logger.info(f"Connecting to HTTP RPC: {settings.base_rpc[:50]}...")
        w3 = Web3(Web3.HTTPProvider(settings.base_rpc))
    
    if w3.is_connected():
        logger.info("✅ Web3 connection established")
    else:
        logger.error("❌ Web3 connection failed")
        sys.exit(1)
except Exception as e:
    logger.error(f"Web3 initialization error: {e}")
    sys.exit(1)

# Initialize scanners
order_flow_scanner = OrderFlowImbalance(w3) if settings.enable_order_flow else None
circuit_breaker = CircuitBreakerV2() if settings.enable_circuit_breaker else None

logger.info("✅ Async Executor initialized with upgrades")

async def poll_blockchain():
    """Main blockchain polling loop with order flow scanning"""
    print(f"[AsyncExecutor] Starting Async Block Listener (Base 2s block time)...")
    last_block = None
    signal_count = 0
    
    while True:
        try:
            current_block = w3.eth.block_number
            
            if current_block != last_block:
                print(f"[AsyncExecutor] Starting from live block {current_block}")
                last_block = current_block
                
                # Scan order flow every 10 blocks
                if settings.enable_order_flow and order_flow_scanner and current_block % 10 == 0:
                    flow_signals = await order_flow_scanner.scan_mempool_imbalance()
                    
                    for signal in flow_signals:
                        signal_count += 1
                        
                        # Check circuit breaker before logging signal
                        if circuit_breaker:
                            safety_check = await circuit_breaker.check_anomaly(signal['token'], w3)
                            if safety_check['action'] == 'BLOCK_TRADE':
                                logger.warning(f"🚫 Circuit breaker blocked signal: {safety_check['reason']}")
                                continue
                        
                        logger.info(
                            f"📊 ORDER FLOW SIGNAL #{signal_count} | "
                            f"Token: {signal['token'][:10]}... | "
                            f"Ratio: {signal['buy_sell_ratio']:.1f}:1 | "
                            f"Flow: {signal['total_flow_eth']:.2f} ETH | "
                            f"Buyers: {signal['unique_buyers']} | "
                            f"Confidence: {signal['confidence']:.0f}%"
                        )
                        
                        # Here you would route to execution engine
                        # For now, just log the signal
                        await log_signal_to_db(signal)
                
                await asyncio.sleep(2)  # Base block time
            else:
                await asyncio.sleep(1)
                
        except Exception as e:
            logger.error(f"[AsyncExecutor] Polling error: {e}")
            await asyncio.sleep(5)

async def log_signal_to_db(signal: dict):
    """Log signal to database for tracking"""
    try:
        import sqlite3
        conn = sqlite3.connect(settings.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT OR IGNORE INTO alpha_signals 
            (signal_type, tx_hash, ai_score, status, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (
            signal.get('signal_type', 'order_flow'),
            f"signal_{int(time.time())}_{signal['token'][:8]}",
            signal.get('confidence', 50),
            'PENDING',
            datetime.utcnow().isoformat()
        ))
        
        conn.commit()
        conn.close()
        logger.info(f"✅ Signal logged to database")
        
    except Exception as e:
        logger.error(f"Failed to log signal: {e}")

# =============================================================================
# 🚨 ENTRY POINT
# =============================================================================
async def main():
    print("🚀 AlphaPulse Dual-Process Engine Initializing...")
    print(f"📡 Using port: {os.environ.get('PORT', 7860)}")
    print(f"🔧 Features: OrderFlow={settings.enable_order_flow}, CircuitBreaker={settings.enable_circuit_breaker}")
    print("✅ Async Executor started in background")
    
    # Start blockchain polling
    await poll_blockchain()

if __name__ == "__main__":
    # Run the async main loop
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("🛑 Shutdown requested")
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        sys.exit(1)
