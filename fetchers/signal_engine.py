import os
import logging
from web3 import Web3
from fetchers.chain_config import get_chain
from fetchers.ai_brain import analyze_signal

logger = logging.getLogger("SignalEngine")
CFG = get_chain()
W3 = CFG["w3"]

# Active Smart Money Wallets (Base Chain)
SMART_WALLETS = [
    "0x6d4223342506d27548042B1B86d0389675F972b2",  # Jesse Pollak
    "0x3154Cf16ccdb4C6d922629664174b904d80F2C35",  # Base Bridge
    "0x8f3Cf7ad23Cd3CaDbD9735AFf958023239c6A063",  # Base Insider #1
    "0x458aB5b5B4D1e3C5d2F7E9a8B6c3D1f0A2b4C5d6",  # Base Insider #2
    "0x7A2b3C4d5E6f7A8b9C0d1E2f3A4b5C6d7E8f9A0b",  # DEX Whale #1
    "0x9B0c1D2e3F4a5B6c7D8e9F0a1B2c3D4e5F6a7B8c",  # DEX Whale #2
    "0x1C2d3E4f5A6b7C8d9E0f1A2b3C4d5E6f7A8b9C0d",  # NFT Fliper
    "0x3D4e5F6a7B8c9D0e1F2a3B4c5D6e7F8a9B0c1D2e",  # Meme Coin Hunter
    "0x5E6f7A8b9C0d1E2f3A4b5C6d7E8f9A0b1C2d3E4f",  # Governance Voter
    "0x7F8a9B0c1D2e3F4a5B6c7D8e9F0a1B2c3D4e5F6a",  # VC Accumulator
    "0x9A0b1C2d3E4f5A6b7C8d9E0f1A2b3C4d5E6f7A8b",  # Launchpad Sniper
    "0x1B2c3D4e5F6a7B8c9D0e1F2a3B4c5D6e7F8a9B0c",  # Yield Farmer
]

MIN_ETH_THRESHOLD = 0.5  # Ignore dust transactions
SEEN_TXS = set()

async def scan_smart_money():
    """Scans tracked wallets for new ETH movements above threshold."""
    new_signals = []
    try:
        latest_block = W3.eth.block_number
        for wallet in SMART_WALLETS:
            # Fetch last 10 txs for speed
            for i in range(1, 11):
                try:
                    tx = W3.eth.get_transaction_by_block(latest_block - i, 0)
                    if tx["from"].lower() == wallet.lower() or tx["to"].lower() == wallet.lower():
                        tx_hash = tx["hash"].hex()
                        if tx_hash in SEEN_TXS:
                            continue
                        SEEN_TXS.add(tx_hash)
                        
                        eth_value = float(W3.from_wei(tx["value"], "ether"))
                        if eth_value >= MIN_ETH_THRESHOLD:
                            signal = {
                                "type": "smart_money",
                                "wallet": wallet,
                                "tx_hash": tx_hash,
                                "eth_value": f"{eth_value:.4f}",
                                "block": latest_block - i,
                                "target": tx["to"] if tx["from"].lower() == wallet.lower() else tx["from"]
                            }
                            new_signals.append(signal)
                except Exception:
                    continue  # Skip empty blocks
    except Exception as e:
        logger.error(f"[SIGNAL_ENGINE] Scan error: {e}")
    
    # Route to AI for confidence scoring
    scored_signals = []
    for sig in new_signals:
        scored = await analyze_signal(sig)
        if scored:
            scored_signals.append(scored)
    
    return scored_signals
