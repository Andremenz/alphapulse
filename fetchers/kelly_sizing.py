import os
from web3 import Web3

# Base Chain Config (mirrors trading_engine.py)
BASE_RPC_URL = "https://mainnet.base.org"
W3 = Web3(Web3.HTTPProvider(BASE_RPC_URL))

def calculate_optimal_position_size(ai_score: int, liquidity_usd: float, wallet_balance_wei: int) -> int:
    BASE_SIZE_ETH = 0.003
    MIN_SIZE_ETH = 0.0015
    MAX_PORTFOLIO_PCT = 0.25
    GAS_RESERVE_ETH = 0.002
    
    balance_eth = W3.from_wei(wallet_balance_wei, "ether")
    available_eth = max(0, balance_eth - GAS_RESERVE_ETH)
    
    if available_eth < MIN_SIZE_ETH:
        return 0
    
    # Confidence Multiplier (0.6x to 1.3x)
    conf_mult = max(0.6, min(1.3, (ai_score - 75) / 25))
    
    # Liquidity Multiplier (0.5x to 1.5x)
    if liquidity_usd >= 3_000_000: liq_mult = 1.5
    elif liquidity_usd >= 1_000_000: liq_mult = 1.2
    elif liquidity_usd >= 250_000: liq_mult = 0.9
    else: liq_mult = 0.6
    
    raw_size = BASE_SIZE_ETH * conf_mult * liq_mult
    max_allowed = available_eth * MAX_PORTFOLIO_PCT
    final_size = min(raw_size, max_allowed)
    
    if final_size < MIN_SIZE_ETH: return 0
        
    print(f"[KELLY] 📏 AI: {ai_score}/100 | Liq: ${liquidity_usd:,.0f} | Raw: {raw_size:.4f} ETH")
    print(f"[KELLY] 🎯 Final: {final_size:.4f} ETH (Available: {available_eth:.4f} ETH)")
    
    return W3.to_wei(final_size, "ether")
