import os
import json
import sqlite3
import uuid
import httpx
from datetime import datetime
from fetchers.shadow_ledger import DB_PATH

PENDING_FILE = "data/pending_proposals.json"

async def propose_prompt_update(proposal_id: str, space: str, ai_score: int, entry_price: float, exit_price: float):
    """Analyzes trade outcome and proposes prompt refinements if AI confidence mismatched actual PnL."""
    actual_pnl = ((exit_price - entry_price) / entry_price) * 100
    
    # Only propose if mismatch is significant (>15% deviation from expected)
    expected_direction = "positive" if ai_score >= 80 else "negative"
    actual_direction = "positive" if actual_pnl > 0 else "negative"
    
    if expected_direction == actual_direction:
        print(f"[PROMPT] ✅ AI prediction aligned with outcome for {space}. No update needed.")
        return None

    # Load current prompts
    try:
        with open("data/active_prompts.json", "r") as f:
            prompts = json.load(f)
    except FileNotFoundError:
        return None

    current_prompt = prompts.get("governance" if space.lower() in ["aerodrome", "baseswap", "brett"] else "code", "")
    
    # Ask Groq for refinement
    meta_prompt = f"""Current Prompt:\n{current_prompt}\n\nTrade Result:\n- AI Confidence: {ai_score}/100\n- Actual PnL: {actual_pnl:.2f}%\n- Direction Mismatch: AI predicted {expected_direction}, market went {actual_direction}\n\nTask: Propose a refined version of the prompt that better calibrates scoring for this type of event. Keep the same JSON output format. Return ONLY the refined prompt text."""
    
    groq_key = os.environ.get("GROQ_API_KEY")
    if not groq_key: return None
    
    headers = {"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"}
    payload = {"model": "llama3-70b-8192", "messages": [{"role": "user", "content": meta_prompt}], "temperature": 0.3}
    
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload, timeout=15.0)
            resp.raise_for_status()
            new_prompt = resp.json()["choices"][0]["message"]["content"].strip()
        except Exception:
            return None

    proposal_id = str(uuid.uuid4())[:8]
    proposal = {
        "id": proposal_id,
        "type": "governance" if space.lower() in ["aerodrome", "baseswap", "brett"] else "code",
        "old_score": ai_score,
        "actual_pnl": f"{actual_pnl:.2f}%",
        "new_prompt": new_prompt,
        "status": "PENDING",
        "timestamp": datetime.utcnow().isoformat()
    }

    # Save to pending file
    try:
        with open(PENDING_FILE, "r") as f: pending = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError): pending = []
    
    pending.append(proposal)
    with open(PENDING_FILE, "w") as f: json.dump(pending, f, indent=2)
    
    print(f"[PROMPT] 🧠 Proposal generated: {proposal_id} | PnL: {actual_pnl:.2f}% | AI: {ai_score}/100")
    
    return {
        "id": f"prompt_{proposal_id}",
        "type": "prompt_proposal",
        "proposal_id": proposal_id,
        "pnl": f"{actual_pnl:.2f}%",
        "ai_score": ai_score,
        "timestamp": datetime.utcnow().isoformat()
    }
