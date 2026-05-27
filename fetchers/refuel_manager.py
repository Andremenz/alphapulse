import os
from web3 import Web3
from fetchers.chain_config import get_chain
from notifiers.platform_notifier import send_notifications

CFG = get_chain()
W3 = CFG["w3"]

# Thresholds for Gas Health
CRITICAL_GAS_ETH = 0.008  # ~$16. Refuel immediately via Orbiter/Symbiosis.
WARNING_GAS_ETH = 0.020   # ~$40. Refuel soon to maintain autonomy.

async def check_gas_and_refuel():
    """
    Monitors wallet balance. If gas is low, sends an urgent Telegram alert
    with a direct link to a permissionless bridge.
    """
    private_key = os.environ.get("BASE_PRIVATE_KEY")
    if not private_key: 
        return

    try:
        account = W3.eth.account.from_key(private_key)
        wallet = account.address
        balance_wei = W3.eth.get_balance(wallet)
        balance_eth = float(W3.from_wei(balance_wei, "ether"))

        alert = None
        
        # Determine Alert Level
        if balance_eth < CRITICAL_GAS_ETH:
            alert = {
                "type": "gas_refuel_alert",
                "level": "CRITICAL",
                "balance": f"{balance_eth:.4f}",
                "wallet": wallet,
                "message": "🚨 GAS CRITICALLY LOW. BOT WILL STOP SOON. REFUEL IMMEDIATELY."
            }
        elif balance_eth < WARNING_GAS_ETH:
            alert = {
                "type": "gas_refuel_alert",
                "level": "WARNING",
                "balance": f"{balance_eth:.4f}",
                "wallet": wallet,
                "message": "⚠️ Gas level low. Refuel recommended to ensure continuous operation."
            }

        # Send Alert if Needed
        if alert:
            await send_notifications([alert])
            
    except Exception as e:
        print(f"[REFUEL] Error checking gas: {e}")
