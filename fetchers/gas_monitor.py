import os
from web3 import Web3
from datetime import datetime

BASE_RPC_URL = "https://mainnet.base.org"
W3 = Web3(Web3.HTTPProvider(BASE_RPC_URL))

async def check_gas_health():
    private_key = os.environ.get("BASE_PRIVATE_KEY")
    if not private_key:
        return

    account = W3.eth.account.from_key(private_key)
    wallet_address = account.address
    balance_wei = W3.eth.get_balance(wallet_address)
    balance_eth = W3.from_wei(balance_wei, "ether")

    # Institutional Thresholds
    CRITICAL_ETH = 0.008  # ~$16 (Gas reserve + 1 emergency exit)
    LOW_ETH = 0.020       # ~$40 (Refuel recommended)

    # Estimate remaining shots (Kelly avg ~$12-25/trade + $4 gas buffer)
    avg_cost_per_trade = 0.015
    shots_left = max(0, (balance_eth - 0.002) / avg_cost_per_trade)

    alert_level = "HEALTHY"
    if balance_eth < CRITICAL_ETH:
        alert_level = "CRITICAL"
    elif balance_eth < LOW_ETH:
        alert_level = "WARNING"

    # Log to Railway console
    print(f"[GAS] 💰 Balance: {balance_eth:.4f} ETH | Est. Shots: {shots_left:.1f} | Status: {alert_level}")

    # Yield alert only if action is needed
    if alert_level != "HEALTHY":
        yield {
            "id": f"gas_{int(datetime.utcnow().timestamp())}",
            "type": "gas_alert",
            "level": alert_level,
            "balance_eth": f"{balance_eth:.4f}",
            "shots_left": f"{shots_left:.1f}",
            "timestamp": datetime.utcnow().isoformat()
        }
