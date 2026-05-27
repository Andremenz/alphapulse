import os
import json
import logging
from web3 import Web3
from fetchers.chain_config import get_chain
from notifiers.platform_notifier import send_notifications

logger = logging.getLogger("RebateTracker")
CFG = get_chain()
W3 = CFG["w3"]
TRACKER_FILE = "data/rebate_tracker.json"

def get_last_balance():
    """Fetches the last tracked balance from local storage."""
    try:
        with open(TRACKER_FILE, "r") as f:
            data = json.load(f)
            return float(data.get("last_balance_eth", 0))
    except Exception:
        return 0.0

def save_last_balance(balance_eth: float):
    """Saves the current balance to local storage for next comparison."""
    os.makedirs("data", exist_ok=True)
    with open(TRACKER_FILE, "w") as f:
        json.dump({"last_balance_eth": str(balance_eth)}, f)

async def check_rebates():
    """Checks wallet balance for positive inflows (MEV Rebates / Profits)."""
    private_key = os.environ.get("BASE_PRIVATE_KEY")
    if not private_key:
        return
    
    try:
        account = W3.eth.account.from_key(private_key)
        wallet = account.address
        
        # Get current balance
        current_wei = W3.eth.get_balance(wallet)
        current_eth = float(W3.from_wei(current_wei, "ether"))
        last_eth = get_last_balance()
        
        # Calculate delta
        diff = current_eth - last_eth
        
        # Always update the tracker to the current balance for the next run
        save_last_balance(current_eth)
        
        # Alert if we detected revenue (Threshold: >0.0005 ETH to filter dust/gas noise)
        # Note: This captures BOTH Trading Profits and MEV Rebates.
        if diff > 0.0005:
            logger.info(f"[REBATE] 💰 Revenue Detected: +{diff:.5f} ETH")
            
            alert_data = {
                "type": "mev_rebate",
                "diff_eth": f"{diff:.5f}",
                "current_eth": f"{current_eth:.4f}",
                "wallet": wallet
            }
            await send_notifications([alert_data])
            
    except Exception as e:
        logger.error(f"[REBATE] Error checking balance: {e}")
