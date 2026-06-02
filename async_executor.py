#!/usr/bin/env python3
"""
AlphaPulse Async Executor - Diagnostic Version
"""
import sys
import os
import asyncio
import logging
import time
import sqlite3
from datetime import datetime
from pathlib import Path
from collections import defaultdict, deque, Counter
from dataclasses import dataclass, field
from typing import Dict, List, Deque
import numpy as np
from web3 import Web3

# =============================================================================
# 1. CONFIGURATION
# =============================================================================
try:
    from config import settings
    print("✅ Loaded config from config.py", flush=True)
except Exception as e:
    print(f"⚠️ Could not import config.py: {e}. Using fallback config.", flush=True)
    class FallbackConfig:
        def __init__(self):
            self.db_path = os.environ.get("DB_PATH", "/data/alphapulse.db")
            self.base_rpc = os.environ.get("BASE_RPC", "https://mainnet.base.org")
            self.base_ws = os.environ.get("BASE_WS", "")
            self.quicknode_ws_enabled = False
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
# 3. INLINE: ORDER FLOW SCANNER (Diagnostic Mode)
# =============================================================================
class OrderFlowImbalance:
    def __init__(self, web3: Web3):
        self.web3 = web3
        self.imbalance_history = defaultdict(lambda: deque(maxlen=20))
        self.entry_threshold = 2.0
        
        # Base DEX Router Addresses
        self.dex_routers = {
            '0xcf77a3ba9a5ca399b7c97c74d54e5b1beb874e43': 'Aerodrome V2',
            '0x2626664c2603336e57b271c5c0b26f421741e481': 'Uniswap V3',
            '0x6bded42c6da8fbf0d2ba55b2fa120c5e0c8d7891': 'SushiSwap',
            '0x327df1e6de05895d2ab08513aadd9313fe505d86': 'BaseSwap',
            '0x2626664c2603336e57b271c5c0b26f421741e481': 'Uniswap V3',
        }
        
        # Comprehensive swap signatures for Base
        self.swap_signatures = {
            # Uniswap V2 / Aerodrome V2 / BaseSwap
            '0x7ff36ab5': 'BUY',   # swapExactETHForTokens
            '0x38ed1739': 'SELL',  # swapExactTokensForETH
            '0xfb3bdb41': 'BUY',   # swapETHForExactTokens
            '0x18cbafe5': 'SELL',  # swapExactTokensForTokens
            '0x4a25d94a': 'SELL',  # swapTokensForExactETH
            '0x5c11d795': 'BUY',   # swapExactTokensForTokensSupportingFeeOnTransferTokens
            '0xb6f9de95': 'BUY',  # swapExactETHForTokensSupportingFeeOnTransferTokens
            '0x791ac947': 'SELL', # swapExactTokensForETHSupportingFeeOnTransferTokens
            
            # Uniswap V3
            '0x414bf389': 'BUY',   # exactInputSingle
            '0xc04b8d59': 'BUY',   # exactInput
            '0xdb3e2198': 'SELL',  # exactOutputSingle
            '0xf28c0498': 'SELL',  # exactOutput
            '0x5ae401dc': 'MIXED', # multicall (contains swaps)
            '0x472b43f3': 'BUY',   # exactInputSingle (alternate)
            '0x09b81346': 'SELL',  # exactOutputSingle (alternate)
            
            # Aerodrome specific
            '0x9b2c0a37': 'BUY',   # swapExactTokensForTokens
            '0xe8e33700': 'BUY',   # addLiquidity (often paired with buys)
            '0xbaa2ab': 'SELL',   # removeLiquidity
        }
        
        # Track method IDs for diagnostics
        self.method_id_counter = Counter()
        self.diagnostic_logged = False
        
        logger.info("✅ OrderFlowImbalance scanner initialized (Diagnostic Mode)")
    
    async def scan_mempool_imbalance(self) -> List[Dict]:
        try:
            current_block = self.web3.eth.block_number 
            token_flows = defaultdict(lambda: {'buys': 0, 'sells': 0, 'total_eth': 0, 'unique_buyers': set()})
            
            # Scan last 3 blocks
            for i in range(3):
                block_num = current_block - i
                try:
                    block = self.web3.eth.get_block(block_num, full_transactions=True) 
                    
                    for tx in block.transactions:
                        # DIAGNOSTIC: Log first 20 method IDs we see
                        if not self.diagnostic_logged and len(self.method_id_counter) < 20:
                            if hasattr(tx, 'input') and tx.input and len(tx.input) >= 4:
                                if isinstance(tx.input, bytes):
                                    method_id = '0x' + tx.input[:4].hex()
                                else:
                                    method_id = str(tx.input)[:10]
                                self.method_id_counter[method_id] += 1
                        
                        decoded = self._decode_swap(tx)
                        if decoded:
                            direction = 'buys' if decoded['type'] == 'BUY' else 'sells'
                            token_flows[decoded['token']][direction] += 1
                            token_flows[decoded['token']]['total_eth'] += decoded['eth_value']
                            if direction == 'buys':
                                token_flows[decoded['token']]['unique_buyers'].add(decoded['from_addr'])
                except Exception as e:
                    logger.error(f"Block fetch error {block_num}: {e}")
                    continue
            
            # DIAGNOSTIC: Log top method IDs once
            if not self.diagnostic_logged and len(self.method_id_counter) > 0:
                logger.info("🔍 DIAGNOSTIC: Top 10 method IDs found in transactions:")
                for method_id, count in self.method_id_counter.most_common(10):
                    logger.info(f"   {method_id}: {count} times")
                self.diagnostic_logged = True
            
            total_swaps = sum(f['buys'] + f['sells'] for f in token_flows.values())
            
            if total_swaps > 0:
                sorted_tokens = sorted(token_flows.items(), key=lambda x: x[1]['total_eth'], reverse=True)[:3]
                for token, flows in sorted_tokens:
                    ratio = flows['buys'] / max(flows['sells'], 1) if flows['sells'] > 0 else flows['buys'] * 2
                    logger.info(
                        f"   → {token[:10]}... | "
                        f"Buys: {flows['buys']} | Sells: {flows['sells']} | "
                        f"Ratio: {ratio:.1f}:1 | "
                        f"Flow: {flows['total_eth'] / 1e18:.2f} ETH"
                    )
            
            signals = []
            for token, flows in token_flows.items():
                if flows['sells'] > 0:
                    ratio = flows['buys'] / max(flows['sells'], 1)
                else:
                    ratio = flows['buys'] * 2 if flows['buys'] > 0 else 0
                
                self.imbalance_history[token].append(ratio)
                
                if flows['buys'] >= 2 and ratio >= self.entry_threshold:
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
            logger.error(f"Scanner error: {e}", exc_info=True)
            return []
    
    def _decode_swap(self, tx) -> Dict:
        try:
            if not hasattr(tx, 'input') or not tx.input or len(tx.input) < 10:
                return None
            
            if isinstance(tx.input, bytes):
                method_id = '0x' + tx.input[:4].hex()
            else:
                method_id = str(tx.input)[:10]
            
            # Check if this is a known swap method
            if method_id not in self.swap_signatures:
                return None
            
            swap_type = self.swap_signatures[method_id]
            
            # For multicall, we'd need to decode further - skip for now
            if swap_type == 'MIXED':
                return None
            
            is_buy = swap_type == 'BUY'
            eth_value = tx.value if hasattr(tx, 'value') else 0
            
            # Get the router address (tx.to)
            router_address = tx.to.lower() if hasattr(tx, 'to') and tx.to else None
            
            # For buys, the token is in the path (we'd need to decode input data)
            # For now, use the router address as a proxy
            if not router_address:
                return None
            
            # Skip if no ETH value for buys
            if is_buy and eth_value == 0:
                return None
            
            return {
                'type': 'BUY' if is_buy else 'SELL',
                'token': router_address,  # Using router as proxy for now
                'eth_value': eth_value,
                'from_addr': tx.get('from', '').lower(),
                'router': router_address,
                'dex': self.dex_routers.get(router_address, 'Unknown')
            }
        except Exception as e:
            logger.debug(f"Decode error: {e}")
            return None

# =============================================================================
# 4. INLINE: CIRCUIT BREAKER V2
# =============================================================================
@dataclass
class CircuitBreakerV2:
    z_score_threshold: float = 3.0
    
    async def check_anomaly(self, token_address: str, web3: Web3) -> Dict:
        try:
            current_block = web3.eth.block_number 
            volumes = []
            for block_num in range(current_block - 10, current_block):
                try:
                    block = web3.eth.get_block(block_num, full_transactions=False) 
                    volumes.append(len(block.transactions))
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
    rpc_url = settings.base_rpc
    logger.info(f"Connecting to HTTP RPC: {rpc_url[:50]}...")
    w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={'timeout': 10}))
    
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
    print(f"[AsyncExecutor] Starting Async Block Listener...", flush=True)
    last_block = None
    signal_count = 0
    
    while True:
        try:
            current_block = w3.eth.block_number
            
            if current_block != last_block:
                if current_block % 10 == 0:
                    print(f"[AsyncExecutor] Live block {current_block}", flush=True)
                last_block = current_block
                
                if settings.enable_order_flow and order_flow_scanner and current_block % 5 == 0:
                    try:
                        flow_signals = await order_flow_scanner.scan_mempool_imbalance()
                        
                        for signal in flow_signals:
                            signal_count += 1
                            
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
                    except Exception as e:
                        logger.error(f"Scanner execution error: {e}", exc_info=True)
                
                await asyncio.sleep(2)
            else:
                await asyncio.sleep(1)
                
        except Exception as e:
            logger.error(f"[AsyncExecutor] Polling error: {e}", exc_info=True)
            await asyncio.sleep(5)

async def log_signal_to_db(signal: dict):
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
    print("🚀 AlphaPulse Dual-Process Engine Initializing...", flush=True)
    print(f"📡 Using port: {os.environ.get('PORT', 7860)}", flush=True)
    print("✅ Async Executor started in background", flush=True)
    await poll_blockchain()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("🛑 Shutdown requested", flush=True)
    except Exception as e:
        print(f"❌ Fatal error: {e}", flush=True)
        sys.exit(1)
