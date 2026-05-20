import httpx
from web3 import Web3
from config import settings
from typing import List, Dict
import os

def get_rpc_url(chain: str) -> str:
    if chain == "ethereum":
        return f"https://eth-mainnet.g.alchemy.com/v2/{settings.alchemy_api_key}"
    elif chain == "base":
        return f"https://base-mainnet.g.alchemy.com/v2/{settings.alchemy_api_key}"
    elif chain == "arbitrum":
        return f"https://arb-mainnet.g.alchemy.com/v2/{settings.alchemy_api_key}"
    return f"https://{chain}-mainnet.g.alchemy.com/v2/{settings.alchemy_api_key}"

async def resolve_ens(address: str, chain: str = "ethereum") -> str:
    try:
        w3 = Web3(Web3.HTTPProvider(get_rpc_url(chain)))
        return w3.ens.name(address) or "Unknown"
    except:
        return "Unknown"

async def get_token_price_change(symbol: str, hours: int = 2) -> float:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"https://api.coingecko.com/api/v3/simple/price?ids={symbol}&vs_currencies=usd&include_24hr_change=true")
            data = resp.json()
            return data.get(symbol, {}).get("usd_24h_change", 0.0)
    except:
        return 0.0

async def run_intelligence_scan(vesting_alerts: List[Dict], config: Dict) -> List[Dict]:
    intelligence_alerts = []
    known_entities = config.get("known_entities", {})
    price_threshold = config.get("price_threshold_percent", 5.0)

    for alert in vesting_alerts:
        beneficiary = alert.get("beneficiary", "")
        amount = alert.get("amount_eth", 0)
        chain = alert.get("chain", "ethereum")
        tx_hash = alert.get("tx_hash", "")
        
        # 1. Entity Resolution
        entity_name = known_entities.get(beneficiary.lower(), "Unknown Wallet")
        if entity_name == "Unknown Wallet":
            entity_name = await resolve_ens(beneficiary, chain)
            if entity_name != "Unknown":
                entity_name = f"ENS: {entity_name}"

        # 2. Insider Pattern Detection
        price_change = await get_token_price_change(chain, 2)
        risk_score = 0
        flags = []
        
        if abs(price_change) > price_threshold:
            risk_score += 2
            flags.append(f"Price moved {price_change:.1f}% in 2h")
        if "Hot Wallet" in entity_name or "Binance" in entity_name or "Coinbase" in entity_name:
            risk_score += 3
            flags.append("Transfer to known CEX/Hot Wallet")
        if amount > 50:
            risk_score += 2
            flags.append(f"Large amount: {amount:.2f} ETH")

        if risk_score >= 3:
            intelligence_alerts.append({
                "type": "intelligence_alert",
                "title": "️ HIGH RISK VESTING ACTIVITY",
                "entity": entity_name,
                "amount": f"{amount:.4f} ETH",
                "chain": chain.title(),
                "risk_score": risk_score,
                "flags": " | ".join(flags),
                "tx": f"https://{chain}.etherscan.io/tx/{tx_hash}" if chain == "ethereum" else f"https://{chain}scan.org/tx/{tx_hash}",
                "timestamp": alert.get("timestamp", "Now")
            })
            
    return intelligence_alerts
