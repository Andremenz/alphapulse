#!/usr/bin/env python3
"""
AlphaPulse Async Executor - Monolithic Version
All logic contained in a single file to bypass Hugging Face package import issues.
"""
import sys
import os
import asyncio
import logging
import time
import sqlite3
from datetime import datetime
from pathlib import Path
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Dict, List, Deque
import numpy as np
from web3 import Web3

# =============================================================================
# 1. CONFIGURATION (Inline fallback to guarantee it runs)
# =============================================================================
try:
    from config import settings
    print("✅ Loaded config from config.py")
except Exception as e:
    print(f"⚠️ Could not import config.py: {e}. Using fallback config.")
    class FallbackConfig:
        def __init__(self):
            self.db_path = os.environ.get("DB_PATH", "/data/alphapulse.db")
            self.base_rpc = os.environ.get("BASE_RPC", "https://mainnet.base.org")
            self.base_ws = os.environ.get("BASE_WS", "")
            self.quicknode_ws_enabled = os.environ.get("QUICKNODE_WS_ENABLED", "false").lower() == "true"
            self.enable_order_flow = os.environ.get("ENABLE_ORDER_FLOW", "true").lower() == "true"
            self.enable_circuit_breaker = os.environ.get("ENABLE_CIRCUIT_BREAKER", "true").lower() == "true"
            Path("/data").mkdir(parents=True, exist_ok=True)
    settings = FallbackConfig()

# =============================================================================
# 2. LOGGING SETUP
# =============================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("AsyncExecutor")

# =============================================================================
# 3. INLINE: ORDER FLOW SCANNER (Upgraded to scan confirmed blocks)
# =============================================================================
class OrderFlowImbalance:
    """Tracks transaction ratio per token by scanning recent blocks."""
    def __init__(self, web3: Web3):
        self.web3 = web3
        self.imbalance_history = defaultdict(lambda: deque(maxlen=20))
        self.entry_threshold = 2.0  # 2:1 buy:sell ratio
        # Common DEX swap method signatures
        self.swap_signatures = {
            '0x7ff36ab5': 'BUY',  # swapExactETHForTokens
            '0x38ed1739': 'SELL', # swapExactTokensForETH
            '0xfb3bdb41': 'BUY',   # swapETHForExactTokens
        }
    
    async def scan_mempool_imbalance(self) -> List[Dict]:
        try:
            current_block = await self.web3.eth.block_number
            token_flows = defaultdict(lambda: {'buys': 0, 'sells': 0, 'total_eth': 0, 'unique_buyers': set()})
            
            # Scan last 5 confirmed blocks for swap activity
            for i in range(5):
                block_num = current_block - i
                try:
                    block = await self.web3.eth.get_block(block_num, full_transactions=True)
                    for tx in block.transactions:
                        decoded = self._decode_swap(tx)
                        if decoded:
                            direction = 'buys' if decoded['type'] == 'BUY' else 'sells'
                            token_flows[decoded['token']][direction] += 1
                            token_flows[decoded['token']]['total_eth'] += decoded['eth_value']
                            if direction == 'buys':
                                token_flows[decoded['token']]['unique_buyers'].add(decoded['from_addr'])
                except Exception:
                    continue
            
            signals = []
            for token, flows in token_flows.items():
                if flows['sells'] > 0:
                    ratio = flows['buys'] / max(flows['sells'], 1)
                else:
                    ratio = flows['buys'] * 2 if flows['buys'] > 0 else 0
                
                self.imbalance_history[token].append(ratio)
                
                # Signal if strong buy pressure in recent blocks (at least 3 buys, 2:1 ratio)
                if flows['buys'] >= 3 and ratio >= self.entry_threshold:
                    signals.append({
                        'token': token,
                        'buy_sell_ratio': ratio,
                        'total_flow_eth': flows['total_eth'] / 1e18,
                        'unique_buyers': len(flows['unique_buyers']),
                        'confidence': min(ratio * 25, 95),
                        'signal_type': 'order_flow_imbalance',
                        'timestamp': time.time()
                    })
            
            return sorted(signals, key=lambda x: x['total_flow_eth'], reverse=True)[:3]
        except Exception as e:
            logger.error(f"Order flow scan error: {e}")
            return []
    
    def _decode_swap(self, tx) -> Dict:
        try:
            if not hasattr(tx, 'input') or not tx.input or len(tx.input) < 10:
                return None
            
            # Get method ID (first 4 bytes)
            if isinstance(tx.input, bytes):
                method_id = '0x' + tx.input[:4].hex()
            else:
                method_id = str(tx.input)[:10]
            
            if method_id not in self.swap_signatures:
                return None
            
            is_buy = self.swap_signatures[method_id] == 'BUY'
            eth_value = tx.value if hasattr(tx, 'value') else 0
            token_address = tx.to if hasattr(tx, 'to') and tx.to else None
            
            if not token_address or eth_value == 0:
                return None
            
            return {
                'type': 'BUY' if is_buy else 'SELL',
                'token': token_address.lower(),
                'eth_value': eth_value,
                'from_addr': tx['from'].lower() if hasattr(tx, 'from') else ''
            }
        except Exception:
            return None

# =============================================================================
# 4. INLINE: CIRCUIT BREAKER V2
# =============================================================================
@dataclass
class CircuitBreakerV2:
    """Volume anomaly detection to prevent rug-pull entries"""
    z_score_threshold: float = 3.0
    
    async def check_anomaly(self, token_address: str, web3: Web3) -> Dict:
        try:
            current_block = await web3.eth.block_number
            volumes = []
            for block_num in range(current_block - 20, current_block):
                try:
                    block = await web3.eth.get_block(block_num, full_transactions=False)
                    volumes.append(len(block.get('transactions', [])))
                except:
                    volumes.append(0)
            
            if len(volumes) < 5 or np.std(volumes) == 0:
                return {"anomaly": False, "action": "ALLOW", "reason": "insufficient_data"}
            
            current_volume = volumes[-1]
            vol_z = (current_volume - np.mean(volumes)) / (np.std(volumes) + 1e-8)
            anomaly_detected = abs(vol_z) > self.z_score_threshold
            
            return {
                "volume_z_score": float(vol_z),
                "anomaly": anomaly_detected,
                "action": "BLOCK_TRADE" if anomaly_detected else "ALLOW",
                "reason": f"z_score={vol_z:.2f}"
            }
        except Exception as e:
            return {"anomaly": False, "action": "ALLOW", "reason": "error_fail_open"}

# =============================================================================
# 5. WEB3 INITIALIZATION
# =============================================================================
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

logger.info("✅ Async Executor initialized (Monolithic Mode)")
logger.info(f"🔧 Features: OrderFlow={settings.enable_order_flow}, CircuitBreaker={settings.enable_circuit_breaker}")

# =============================================================================
# 6. MAIN POLLING LOOP
# =============================================================================
async def poll_blockchain():
    print(f"[AsyncExecutor] Starting Async Block Listener...")
    last_block = None
    signal_count = 0
    
    while True:
        try:
            current_block = w3.eth.block_number
            
            if current_block != last_block:
                if current_block % 10 == 0:
                    print(f"[AsyncExecutor] Live block {current_block}")
                last_block = current_block
                
                # Scan order flow every 5 blocks (approx every 10 seconds)
                if settings.enable_order_flow and order_flow_scanner and current_block % 5 == 0:
                    flow_signals = await order_flow_scanner.scan_mempool_imbalance()
                    
                    for signal in flow_signals:
                        signal_count += 1
                        
                        # Check circuit breaker before logging signal
                        if circuit_breaker:
                            safety_check = await circuit_breaker.check_anomaly(signal['token'], w3)
                            if safety_check['action'] == 'BLOCK_TRADE':
                                logger.warning(f"🚫 Circuit breaker blocked: {safety_check['reason']}")
                                continue
                        
                        logger.info(
                            f"📊 SIGNAL #{signal_count} | "
                            f"Token: {signal['token'][:10]}... | "
                            f"Ratio: {signal['buy_sell_ratio']:.1f}:1 | "
                            f"Flow: {signal['total_flow_eth']:.2f} ETH | "
                            f"Buyers: {signal['unique_buyers']} | "
                            f"Confidence: {signal['confidence']:.0f}%"
                        )
                        await log_signal_to_db(signal)
                
                await asyncio.sleep(2)
            else:
                await asyncio.sleep(1)
                
        except Exception as e:
            logger.error(f"[AsyncExecutor] Polling error: {e}")
            await asyncio.sleep(5)

async def log_signal_to_db(signal: dict):
    """Persist signals to SQLite for the dashboard"""
    try:
        conn = sqlite3.connect(settings.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS alpha_signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                signal_type TEXT, tx_hash TEXT UNIQUE, ai_score INTEGER, 
                status TEXT, created_at TEXT
            )
        """)
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
    except Exception as e:
        logger.error(f"DB log error: {e}")

async def main():
    print("🚀 AlphaPulse Dual-Process Engine Initializing...")
    print(f"📡 Using port: {os.environ.get('PORT', 7860)}")
    print("✅ Async Executor started in background")
    await poll_blockchain()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("🛑 Shutdown requested")
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        sys.exit(1)
