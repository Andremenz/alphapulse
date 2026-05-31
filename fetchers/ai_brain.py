import os
import logging
from groq import Groq

logger = logging.getLogger("AIBrain")
GROQ_KEY = os.environ.get("GROQ_API_KEY")
client = Groq(api_key=GROQ_KEY) if GROQ_KEY else None

# Dynamic threshold: starts low, tightens as win-rate improves
BASE_THRESHOLD = 60
WIN_RATE_THRESHOLD = 75  # Tighten to 75% after 5+ wins

async def analyze_signal(signal: dict) -> dict | None:
    if not client:
        logger.warning("[AIBRAIN] Groq API key missing. Skipping AI scoring.")
        return signal  # Fallback: pass raw signal
    
    prompt = f"""
    Analyze this on-chain signal for trading potential on Base chain:
    - Type: {signal.get('type')}
    - Wallet: {signal.get('wallet', 'Unknown')}
    - ETH Value: {signal.get('eth_value', '0')}
    - Target Address: {signal.get('target', 'Unknown')}
    
    Score from 0-100 based on:
    1. Wallet reputation (insider/whale vs random)
    2. Transaction size relative to typical Base activity
    3. Target address pattern (contract interaction vs EOA)
    4. Timing urgency
    
    Return ONLY a JSON object: {{"score": 0-100, "reasoning": "1 sentence", "action": "SNIPE" if score>60 else "IGNORE"}}
    """
    
    try:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=150
        )
        import json
        result = json.loads(response.choices[0].message.content)
        signal["ai_score"] = result.get("score", 0)
        signal["ai_reasoning"] = result.get("reasoning", "")
        signal["ai_action"] = result.get("action", "IGNORE")
        
        # Dynamic threshold check
        threshold = BASE_THRESHOLD
        # (In production, fetch live win-rate from Shadow Ledger here)
        if signal["ai_score"] >= threshold:
            return signal
        return None
    except Exception as e:
        logger.error(f"[AIBRAIN] AI scoring failed: {e}")
        return None
