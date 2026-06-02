import asyncio
from collections import defaultdict, deque
from typing import Dict, List
from web3 import Web3
import logging
import time

logger = logging.getLogger("OrderFlowScanner")

class OrderFlowImbalance:
    """
    Tracks pending transaction ratio per token.
    When BUY:SELL ratio > 3:1 for 5+ blocks, generates a signal.
    """
    
    def __init__(self, web3: Web3):
        self.web3 = web3
        self.imbalance_history = defaultdict(lambda: deque(maxlen=20))
        self.entry_threshold = 3.0  # 3:1 buy:sell ratio
        self.position_size_pct = 0.02  # 2% of portfolio per signal
        
        # Known DEX router addresses for Base
        self.dex_routers = {
            '0xcF77a3Ba9A5CA399B7c97c74d54e5b1Beb874E43': 'Aerodrome',
            '0x2626664c2603336E57B271c5C0b26F421741e481': 'Uniswap V3',
            '0x6BDED42c6DA8FBf0d2bA55B2fa120C5e0c8D7891': 'SushiSwap',
        }
        
        # Swap method signatures
        self.swap_signatures = {
            '0x7ff36ab5': 'swapExactETHForTokens',  # BUY
            '0x38ed1739': 'swapExactTokensForETH',  # SELL
            '0x18cbafe5': 'swapExactTokensForTokens',
        }
    
    async def scan_mempool_imbalance(self) -> List[Dict]:
        """Calculate buy/sell ratio for every token in pending transactions"""
        try:
            pending_block = await self.web3.eth.get_block('pending', full_transactions=True)
            
            token_flows = defaultdict(lambda: {'buys': 0, 'sells': 0, 'total_eth': 0, 'unique_buyers': set()})
            
            for tx in pending_block.transactions:
                decoded = self._decode_swap(tx)
                if decoded:
                    direction = 'buys' if decoded['type'] == 'BUY' else 'sells'
                    token_flows[decoded['token']][direction] += 1
                    token_flows[decoded['token']]['total_eth'] += decoded['eth_value']
                    if direction == 'buys':
                        token_flows[decoded['token']]['unique_buyers'].add(decoded['from_addr'])
            
            # Find tokens with extreme buy pressure
            signals = []
            for token, flows in token_flows.items():
                if flows['sells'] > 0:
                    ratio = flows['buys'] / max(flows['sells'], 1)
                else:
                    ratio = flows['buys'] * 2  # No sells = very bullish
                
                # Update rolling history
                self.imbalance_history[token].append(ratio)
                
                # Signal if sustained imbalance (>3:1 for 5+ blocks)
                recent_history = list(self.imbalance_history[token])[-5:]
                if len(recent_history) >= 3 and all(r > self.entry_threshold for r in recent_history):
                    
                    signals.append({
                        'token': token,
                        'buy_sell_ratio': ratio,
                        'total_flow_eth': flows['total_eth'] / 1e18,
                        'unique_buyers': len(flows['unique_buyers']),
                        'sustained_blocks': len([r for r in recent_history if r > self.entry_threshold]),
                        'action': 'BUY',
                        'confidence': min(ratio / self.entry_threshold * 50, 95),  # Scale to 0-95
                        'signal_type': 'order_flow_imbalance',
                        'timestamp': time.time()
                    })
            
            return sorted(signals, key=lambda x: x['total_flow_eth'], reverse=True)[:5]  # Top 5
            
        except Exception as e:
            logger.error(f"Order flow scan error: {e}")
            return []
    
    def _decode_swap(self, tx) -> Dict:
        """Decode swap transaction to extract token, direction, and value"""
        try:
            # Check if transaction has input data
            if not hasattr(tx, 'input') or not tx.input or len(tx.input) < 10:
                return None
            
            # Get method ID (first 4 bytes)
            method_id = '0x' + tx.input[:8].hex() if isinstance(tx.input, bytes) else tx.input[:10]
            
            # Check if it's a known swap method
            if method_id not in self.swap_signatures:
                return None
            
            # Determine direction
            is_buy = method_id == '0x7ff36ab5'  # swapExactETHForTokens
            
            # Extract value (ETH sent)
            eth_value = tx.value if hasattr(tx, 'value') else 0
            
            # Get token address (simplified - in production would decode path from input data)
            token_address = tx.to if hasattr(tx, 'to') and tx.to else None
            
            if not token_address:
                return None
            
            return {
                'type': 'BUY' if is_buy else 'SELL',
                'token': token_address.lower(),
                'eth_value': eth_value,
                'from_addr': tx['from'].lower() if hasattr(tx, 'from') and tx['from'] else '',
                'method': self.swap_signatures.get(method_id, 'unknown'),
                'dex': self.dex_routers.get(token_address.lower(), 'unknown')
            }
            
        except Exception as e:
            logger.debug(f"Failed to decode transaction: {e}")
            return None
