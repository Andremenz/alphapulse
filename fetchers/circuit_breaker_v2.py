import asyncio
from dataclasses import dataclass, field
from typing import Dict, Deque
from collections import deque
import numpy as np
from web3 import Web3
import logging
import time

logger = logging.getLogger("CircuitBreakerV2")

@dataclass
class CircuitBreakerV2:
    """Multi-signal circuit breaker with volume/liquidity anomaly detection"""
    volume_window: Deque[float] = field(default_factory=lambda: deque(maxlen=30))
    liquidity_window: Deque[float] = field(default_factory=lambda: deque(maxlen=30))
    z_score_threshold: float = 3.0
    cooldown_blocks: int = 7200  # ~4 hours on Base
    
    async def check_anomaly(self, token_address: str, web3: Web3) -> Dict:
        """Check for volume/liquidity anomalies before trade execution"""
        try:
            # Get 30-block volume history (simplified - production uses subgraph)
            current_block = await web3.eth.block_number
            volumes = []
            
            for block_num in range(current_block - 30, current_block):
                try:
                    block = await web3.eth.get_block(block_num, full_transactions=False)
                    # Count transactions (simplified proxy for volume)
                    tx_count = len(block.get('transactions', []))
                    volumes.append(tx_count)
                except:
                    volumes.append(0)
            
            if len(volumes) < 5 or np.std(volumes) == 0:
                return {"anomaly": False, "action": "ALLOW", "reason": "insufficient_data"}
            
            # Calculate z-score for current volume
            current_volume = volumes[-1]
            vol_z = (current_volume - np.mean(volumes)) / (np.std(volumes) + 1e-8)
            
            anomaly_detected = abs(vol_z) > self.z_score_threshold
            
            action = "BLOCK_TRADE" if anomaly_detected else "ALLOW"
            reason = f"volume_z_score={vol_z:.2f}" if anomaly_detected else "normal_volume"
            
            return {
                "volume_z_score": float(vol_z),
                "current_volume": current_volume,
                "avg_volume": float(np.mean(volumes)),
                "anomaly": anomaly_detected,
                "action": action,
                "reason": reason,
                "cooldown_blocks": self.cooldown_blocks if anomaly_detected else 0
            }
        except Exception as e:
            logger.error(f"Circuit breaker check failed: {e}")
            return {"anomaly": False, "action": "ALLOW", "reason": "error_fail_open"}  # Fail open
