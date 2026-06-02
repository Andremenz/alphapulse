#!/usr/bin/env python3
"""
AlphaPulse Async Executor v2.3 - Ultimate Production Ready
Combines: Smart Decoding (v2.2) + On-Chain Receipt Verification (Expert Fix) + Cooldowns
"""
import sys
import os
import asyncio
import logging
import time
import sqlite3
import json
from datetime import datetime, timezone
from pathlib import Path
from collections import defaultdict, deque, Counter
from dataclasses import dataclass
from typing import Dict, List, Optional
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
            self.base_private_key = os.environ.get("BASE_PRIVATE_KEY", "")
            self.enable_order_flow = os.environ.get("ENABLE_ORDER_FLOW", "true").lower() == "true"
            self.enable_circuit_breaker = os.environ.get("ENABLE_CIRCUIT_BREAKER", "true").lower() == "true"
            self.enable_escrow = os.environ.get("ENABLE_ESCROW", "true").lower() == "true"
            self.enable_execution = os.environ.get("ENABLE_EXECUTION", "true").lower() == "true"
            Path("/data").mkdir(parents=True, exist_ok=True)
    settings = FallbackConfig()

# =============================================================================
# 2. LOGGING SETUP & CONSTANTS
# =============================================================================
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s", handlers=[logging.StreamHandler(sys.stdout)])
logger = logging.getLogger("AsyncExecutor")

KNOWN_ROUTERS = [
    '0xcf77a3ba9a5ca399b7c97c74d54e5b1beb874e43', '0x2626664c2603336e57b271c5c0b26f421741e481',
    '0x6bded42c6da8fbf0d2ba55b2fa120c5e0c8d7891', '0x327df1e6de05895d2ab08513aadd9313fe505d86',
    '0x1b8eea9315be45ad17f4a175f5c302f71d5b6b7c', '0x4200000000000000000000000000000000000006',
]

# Minimal ABI to decode swap paths and extract real tokens
MINIMAL_ROUTER_ABI = json.loads('''[
    {"inputs":[{"name":"amountOutMin","type":"uint256"},{"name":"path","type":"address[]"},{"name":"to","type":"address"},{"name":"deadline","type":"uint256"}],"name":"swapExactETHForTokens","outputs":[{"name":"amounts","type":"uint256[]"}],"stateMutability":"payable","type":"function"},
    {"inputs":[{"name":"amountIn","type":"uint256"},{"name":"amountOutMin","type":"uint256"},{"name":"path","type":"address[]"},{"name":"to","type":"address"},{"name":"deadline","type":"uint256"}],"name":"swapExactTokensForETH","outputs":[{"name":"amounts","type":"uint256[]"}],"stateMutability":"nonpayable","type":"function"},
    {"inputs":[{"name":"amountIn","type":"uint256"},{"name":"amountOutMin","type":"uint256"},{"name":"path","type":"address[]"},{"name":"to","type":"address"},{"name":"deadline","type":"uint256"}],"name":"swapExactTokensForTokens","outputs":[{"name":"amounts","type":"uint256[]"}],"stateMutability":"nonpayable","type":"function"}
]''')

TRADE_COOLDOWN = {} 

# =============================================================================
# 3. POSITION ESCROW MANAGER
# =============================================================================
@dataclass
class PositionEscrowManager:
    db_path: str = '/data/alphapulse.db'
    def __post_init__(self):
        self.escrow_stages = [(0, 0.10), (14400, 0.30), (43200, 0.60), (172800, 1.00)]
        self._init_db()
    def _init_db(self):
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("CREATE TABLE IF NOT EXISTS position_escrow (token_address TEXT PRIMARY KEY, total_allocation REAL, first_seen_at TEXT, stage INTEGER DEFAULT 0)")
        except Exception as e: logger.error(f"Escrow DB init error: {e}")
    def compute_releasable_amount(self, token_address: str, total_allocation: float) -> float:
        try:
            now = datetime.now(timezone.utc)
            with sqlite3.connect(self.db_path) as conn:
                row = conn.execute("SELECT first_seen_at, stage FROM position_escrow WHERE token_address=?", (token_address,)).fetchone()
                if row is None:
                    conn.execute("INSERT INTO position_escrow VALUES (?, ?, ?, ?)", (token_address, total_allocation, now.isoformat(), 0))
                    conn.commit()
                    logger.info(f"🔒 New token in escrow: {token_address[:10]}... (10% released)")
                    return total_allocation * 0.10
                first_seen = datetime.fromisoformat(row[0])
                if first_seen.tzinfo is None: first_seen = first_seen.replace(tzinfo=timezone.utc)
                age_seconds = (now - first_seen).total_seconds()
                current_fraction = 0.10
                for threshold, fraction in self.escrow_stages:
                    if age_seconds >= threshold: current_fraction = fraction
                if current_fraction > row[1]:
                    logger.info(f"🔓 Escrow stage up: {token_address[:10]}... now at {current_fraction*100:.0f}%")
                return total_allocation * current_fraction
        except Exception as e: 
            logger.error(f"Escrow computation error: {e}")
            return total_allocation * 0.10

# =============================================================================
# 4. CIRCUIT BREAKER V2
# =============================================================================
@dataclass
class CircuitBreakerV2:
    z_score_threshold: float = 3.0
    def check_anomaly(self, token_address: str, web3: Web3) -> Dict:
        try:
            current_block = web3.eth.block_number
            volumes = []
            for block_num in range(current_block - 10, current_block):
                try:
                    block = web3.eth.get_block(block_num, full_transactions=False)
                    volumes.append(len(block.transactions))
                except: volumes.append(0)
            if len(volumes) < 5 or np.std(volumes) == 0: return {"action": "ALLOW"}
            vol_z = (volumes[-1] - np.mean(volumes)) / (np.std(volumes) + 1e-8)
            return {"action": "BLOCK_TRADE" if abs(vol_z) > self.z_score_threshold else "ALLOW"}
        except: return {"action": "ALLOW"}

# =============================================================================
# 5. ORDER FLOW SCANNER (v2.2 Smart Decoding)
# =============================================================================
class OrderFlowImbalance:
    def __init__(self, web3: Web3):
        self.web3 = web3
        self.imbalance_history = defaultdict(lambda: deque(maxlen=20))
        self.entry_threshold = 2.0
        self.router_contract = self.web3.eth.contract(abi=MINIMAL_ROUTER_ABI)
        self.swap_signatures = {
            '1667d875': 'BUY', '7ff36ab5': 'BUY', '38ed1739': 'SELL', 'fb3bdb41': 'BUY',
            '18cbafe5': 'SELL', '4a25d94a': 'SELL', '5c11d795': 'BUY', 'b6f9de95': 'BUY',
            '791ac947': 'SELL', '03000d00': 'BUY', '03000d01': 'SELL', '02000d00': 'BUY',
            '02000d01': 'SELL', 'effbec13': 'BUY', '6a1edece': 'SELL', '68386927': 'BUY',
            'ff693db0': 'SELL', '6a1ee072': 'BUY', 'd2539b37': 'SELL', '1fad948c': 'BUY',
            'e3ead59e': 'SELL', '95435ac9': 'BUY', 'c7e3ec2c': 'SELL', 'ae7e8d81': 'BUY',
            '6a1eeb3a': 'SELL', 'a00597a0': 'BUY', '6902ca47': 'SELL', '2213bc0b': 'BUY',
            'e3ee160e': 'SELL', '5919af98': 'BUY', '6302b3a1': 'SELL', 'd9238f08': 'BUY',
        }
        self.method_id_counter = Counter()
        self.diagnostic_logged = False
        logger.info("✅ OrderFlowImbalance scanner initialized (v2.3 Ultimate)")
    
    def _extract_method_id(self, tx_input) -> str:
        try:
            if tx_input is None: return ""
            hex_str = tx_input.hex() if hasattr(tx_input, 'hex') else str(tx_input)
            hex_str = hex_str.lower()
            while hex_str.startswith('0x'): hex_str = hex_str[2:]
            return hex_str[:8] if len(hex_str) >= 8 else ""
        except: return ""
    
    def scan_mempool_imbalance(self) -> List[Dict]:
        try:
            current_block = self.web3.eth.block_number
            token_flows = defaultdict(lambda: {'buys': 0, 'sells': 0, 'total_eth': 0, 'unique_buyers': set()})
            for i in range(3):
                try:
                    block = self.web3.eth.get_block(current_block - i, full_transactions=True)
                    for tx in block.transactions:
                        method_id = self._extract_method_id(tx.input if hasattr(tx, 'input') else None)
                        if not self.diagnostic_logged and method_id and len(self.method_id_counter) < 30: self.method_id_counter[method_id] += 1
                        decoded = self._decode_swap(tx, method_id)
                        if decoded:
                            direction = 'buys' if decoded['type'] == 'BUY' else 'sells'
                            token_flows[decoded['token']][direction] += 1
                            token_flows[decoded['token']]['total_eth'] += decoded['eth_value']
                            if direction == 'buys': token_flows[decoded['token']]['unique_buyers'].add(decoded['from_addr'])
                except: continue
            if not self.diagnostic_logged and len(self.method_id_counter) > 0:
                logger.info(f"🔍 DIAGNOSTIC: Sampled transactions. Top IDs: {self.method_id_counter.most_common(5)}")
                self.diagnostic_logged = True
            
            signals = []
            for token, flows in token_flows.items():
                ratio = flows['buys'] / max(flows['sells'], 1) if flows['sells'] > 0 else flows['buys'] * 2
                self.imbalance_history[token].append(ratio)
                if flows['buys'] >= 2 and ratio >= self.entry_threshold:
                    signals.append({'token': token, 'buy_sell_ratio': ratio, 'total_flow_eth': flows['total_eth'] / 1e18, 'unique_buyers': len(flows['unique_buyers']), 'confidence': min(ratio * 25, 95), 'signal_type': 'order_flow_imbalance', 'timestamp': time.time()})
            return sorted(signals, key=lambda x: x['total_flow_eth'], reverse=True)[:3]
        except Exception as e: 
            logger.error(f"Scanner error: {e}")
            return []
    
    def _decode_swap(self, tx, method_id: str) -> Dict:
        try:
            if not method_id or method_id not in self.swap_signatures: return None
            swap_type = self.swap_signatures[method_id]
            if swap_type == 'MIXED': return None
            is_buy = swap_type == 'BUY'
            eth_value = tx.value if hasattr(tx, 'value') else 0
            router_address = tx.to.lower() if hasattr(tx, 'to') and tx.to else None
            if not router_address or (is_buy and eth_value == 0): return None
            
            # 🧠 SMART DECODING: Extract the ACTUAL target token from the swap path
            target_token = None
            try:
                func_obj, func_params = self.router_contract.decode_function_input(tx.input)
                if 'path' in func_params and len(func_params['path']) >= 2:
                    target_token = func_params['path'][-1] # The last token in the path is the target
            except: pass
            
            if not target_token: return None # If we can't decode the real token, skip it
                
            return {'type': 'BUY' if is_buy else 'SELL', 'token': target_token.lower(), 'eth_value': eth_value, 'from_addr': tx.get('from', '').lower() if hasattr(tx, 'get') else getattr(tx, 'from', '').lower()}
        except: return None

# =============================================================================
# 6. EXECUTION ENGINE (v2.3 Expert Fix: On-Chain Verification)
# =============================================================================
async def execute_trade(signal: dict, w3: Web3, private_key: str, escrow_mgr: PositionEscrowManager) -> Optional[str]:
    try:
        token_address = signal['token']
        
        # 🛡️ SAFETY CHECK 1: Do not buy routers or WETH
        if token_address.lower() in KNOWN_ROUTERS:
            logger.info(f"⚠️ Skipping: Target is a router/WETH.")
            return None
            
        # 🛡️ SAFETY CHECK 2: Cooldown (Only trade a token once per hour)
        if token_address in TRADE_COOLDOWN:
            if (time.time() - TRADE_COOLDOWN[token_address]) < 3600:
                logger.info(f"⏳ Cooldown active for {token_address[:10]}... Skipping.")
                return None
        
        base_allocation = w3.to_wei(0.001, 'ether')
        if escrow_mgr: base_allocation = int(escrow_mgr.compute_releasable_amount(token_address, base_allocation))
        if base_allocation < w3.to_wei(0.0001, 'ether'): return None
        
        router_address = "0xcF77a3Ba9A5CA399B7c97c74d54e5b1Beb874E43"
        weth_address = "0x4200000000000000000000000000000000000006"
        abi = json.loads('[{"inputs":[{"name":"amountOutMin","type":"uint256"},{"name":"path","type":"address[]"},{"name":"to","type":"address"},{"name":"deadline","type":"uint256"}],"name":"swapExactETHForTokens","outputs":[{"name":"amounts","type":"uint256[]"}],"stateMutability":"payable","type":"function"}]')
        
        router = w3.eth.contract(address=Web3.to_checksum_address(router_address), abi=abi)
        account = w3.eth.account.from_key(private_key)
        path = [weth_address, Web3.to_checksum_address(token_address)]
        
        tx = router.functions.swapExactETHForTokens(0, path, account.address, int(time.time()) + 60).build_transaction({
            'from': account.address, 'value': base_allocation, 'gas': 350000,
            'gasPrice': w3.eth.gas_price, 'nonce': w3.eth.get_transaction_count(account.address),
        })
        
        # 1. Sign and Broadcast
        signed_tx = account.sign_transaction(tx)
        tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
        
        logger.info(f"⏳ TX Submitted: {tx_hash.hex()}. Waiting for on-chain confirmation...")
        
        # 2. 🛡️ THE EXPERT'S FIX: Wait for the receipt to ensure it didn't revert
        try:
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
        except Exception as e:
            logger.error(f"❌ Timeout waiting for TX receipt: {tx_hash.hex()}")
            return None
            
        # 3. Verify On-Chain Status (Prevents Phantom PnL)
        if receipt['status'] == 0:
            logger.error(f"❌ TX REVERTED ON-CHAIN! (Honeypot/Slippage). Gas wasted, NO tokens received. TX: {tx_hash.hex()}")
            # DO NOT add to cooldown or escrow, because we don't own the token!
            return None 
            
        # 4. Success! Record the cooldown and log
        TRADE_COOLDOWN[token_address] = time.time()
        
        logger.info(f"🚀 TRADE CONFIRMED ON-CHAIN: Bought {token_address[:10]}... for {base_allocation / 1e18:.4f} ETH | TX: {tx_hash.hex()}")
        return tx_hash.hex()
    except Exception as e:
        logger.error(f"❌ Execution error: {e}", exc_info=True)
        return None

# =============================================================================
# 7. MAIN LOOP & INIT
# =============================================================================
try:
    w3 = Web3(Web3.HTTPProvider(settings.base_rpc, request_kwargs={'timeout': 10}))
    if not w3.is_connected(): sys.exit(1)
except Exception as e: sys.exit(1)

order_flow_scanner = OrderFlowImbalance(w3) if settings.enable_order_flow else None
circuit_breaker = CircuitBreakerV2() if settings.enable_circuit_breaker else None
escrow_manager = PositionEscrowManager(db_path=settings.db_path) if settings.enable_escrow else None

logger.info("✅ Async Executor initialized (v2.3 Ultimate)")

async def poll_blockchain():
    print(f"[AsyncExecutor] Starting Async Block Listener...", flush=True)
    last_block = None
    while True:
        try:
            current_block = w3.eth.block_number
            if current_block != last_block:
                if current_block % 10 == 0: print(f"[AsyncExecutor] Live block {current_block}", flush=True)
                last_block = current_block
                if settings.enable_order_flow and order_flow_scanner and current_block % 5 == 0:
                    flow_signals = order_flow_scanner.scan_mempool_imbalance()
                    for signal in flow_signals:
                        if circuit_breaker and circuit_breaker.check_anomaly(signal['token'], w3).get('action') == 'BLOCK_TRADE': continue
                        logger.info(f"📊 SIGNAL | Token: {signal['token'][:10]}... | Ratio: {signal['buy_sell_ratio']:.1f}:1 | Flow: {signal['total_flow_eth']:.2f} ETH")
                        
                        # Log to DB
                        try:
                            conn = sqlite3.connect(settings.db_path)
                            conn.execute("CREATE TABLE IF NOT EXISTS alpha_signals (id INTEGER PRIMARY KEY AUTOINCREMENT, signal_type TEXT, tx_hash TEXT UNIQUE, ai_score INTEGER, status TEXT, created_at TEXT)")
                            conn.execute("INSERT OR IGNORE INTO alpha_signals (signal_type, tx_hash, ai_score, status, created_at) VALUES (?, ?, ?, ?, ?)", (signal.get('signal_type'), f"sig_{int(time.time())}", signal.get('confidence'), 'PENDING', datetime.now(timezone.utc).isoformat()))
                            conn.commit()
                            conn.close()
                        except: pass
                        
                        if settings.enable_execution and settings.base_private_key:
                            await execute_trade(signal, w3, settings.base_private_key, escrow_manager)
                        break
                await asyncio.sleep(2)
            else: await asyncio.sleep(1)
        except Exception as e: await asyncio.sleep(5)

async def main():
    print("🚀 AlphaPulse Engine v2.3 Initializing...", flush=True)
    await poll_blockchain()

if __name__ == "__main__":
    asyncio.run(main())
