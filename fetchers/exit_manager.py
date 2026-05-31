import os
import logging
from web3 import Web3
from fetchers.chain_config import get_chain
from fetchers.aerodrome_router import execute_aerodrome_swap
from fetchers.kelly_sizer import calculate_position_size
from fetchers.shadow_ledger import ipfs_ledger

logger = logging.getLogger("ExitManager")
CFG = get_chain()
W3 = CFG["w3"]

# Trading parameters
TAKE_PROFIT_PCT = 0.15  # 15%
STOP_LOSS_PCT = 0.10    # 10%
SLIPPAGE_PCT = 0.015    # 1.5%

async def check_and_execute_exits():
    """Checks open positions for TP/SL conditions and executes exits."""
    private_key = os.environ.get("BASE_PRIVATE_KEY")
    if not private_key:
        return
    
    try:
        account = W3.eth.account.from_key(private_key)
        wallet = account.address
        
        # Fetch open positions from Shadow Ledger
        open_positions = ipfs_ledger.get_open_positions(wallet)
        
        for pos in open_positions:
            token_address = pos["token_address"]
            entry_price = pos["entry_price"]
            current_price = await _get_token_price(token_address)  # Implement price fetcher
            
            # Check Take-Profit
            if current_price >= entry_price * (1 + TAKE_PROFIT_PCT):
                logger.info(f"[EXIT] 🎯 TP hit for {token_address}! Executing sell...")
                await _execute_exit(pos, "TP", private_key)
            
            # Check Stop-Loss
            elif current_price <= entry_price * (1 - STOP_LOSS_PCT):
                logger.info(f"[EXIT] ⚠️ SL hit for {token_address}! Executing sell...")
                await _execute_exit(pos, "SL", private_key)
                
    except Exception as e:
        logger.error(f"[EXIT] Error checking exits: {e}")

async def _execute_exit(position: dict, reason: str, private_key: str):
    """Executes the exit swap via Aerodrome."""
    try:
        token_address = position["token_address"]
        token_amount = position["token_amount"]
        
        # Calculate output amount with slippage
        result = await execute_aerodrome_swap(
            token_in=token_address,
            token_out="0x4200000000000000000000000000000000000006",  # WETH on Base
            amount_in=token_amount,
            slippage=SLIPPAGE_PCT,
            private_key=private_key
        )
        
        if result["success"]:
            # Record closed trade in Shadow Ledger
            ipfs_ledger.record_trade(
                tx_hash=result["tx_hash"],
                token=token_address,
                entry_price=position["entry_price"],
                exit_price=result["exit_price"],
                reason=reason,
                pnl_pct=result["pnl_pct"]
            )
            logger.info(f"[EXIT] ✅ {reason} exit executed: {result['pnl_pct']:+.1f}% PnL")
        else:
            logger.warning(f"[EXIT] ❌ Exit failed: {result.get('error', 'Unknown')}")
            
    except Exception as e:
        logger.error(f"[EXIT] Execution error: {e}")

async def _get_token_price(token_address: str) -> float:
    """Fetches current token price via GeckoTerminal API."""
    import httpx
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            resp = await client.get(
                f"https://api.geckoterminal.com/api/v2/networks/base/tokens/{token_address}"
            )
            data = resp.json()
            return float(data["data"]["attributes"]["price_usd"])
        except Exception as e:
            logger.warning(f"[PRICE] Failed to fetch price for {token_address}: {e}")
            return 0.0
