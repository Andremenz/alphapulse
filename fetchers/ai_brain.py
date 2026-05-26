import httpx
import json
import os

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

SYSTEM_PROMPT_GOVERNANCE = """You are an elite quantitative analyst and Web3 narrative strategist. Your job is to analyze raw on-chain events and Snapshot governance proposals to identify "Information Asymmetry" (hidden bullish catalysts that retail traders on Twitter do not know about yet).
Evaluate the provided event data and output a strict JSON object. Do not include markdown formatting, explanations, or conversational text. Only output raw JSON.
Scoring Criteria:
- 80-100: Massive catalyst (Token burns, major treasury buybacks, tier-1 partnerships, unexpected tokenomics upgrades). High retail FOMO potential. Action: SNIPE.
- 50-79: Moderate catalyst (Routine grants, minor integrations, standard governance). Low FOMO. Action: MONITOR.
- 0-49: Noise (Multisig transfers, boring parameter tweaks, spam). Action: IGNORE.
JSON Output Format:
{
  "narrative_score": <integer 0-100>,
  "fomo_potential": "<Low, Medium, or High>",
  "reasoning": "<1 sentence explaining the exact financial impact of this event>",
  "action": "<SNIPE, MONITOR, or IGNORE>"
}"""

SYSTEM_PROMPT_CODE = """You are an elite smart contract auditor and Web3 quant. Your job is to analyze GitHub commit messages and code changes from DeFi protocols to identify hidden financial catalysts BEFORE they are announced to the public.
Look for: Fee switches, token burn mechanisms, treasury allocations, buyback functions, or major integrations.
Ignore: Refactoring, typo fixes, CI/CD updates, test updates, and routine chores.
Evaluate the provided commit data and output a strict JSON object. Do not include markdown or conversational text.
JSON Output Format:
{
  "narrative_score": <integer 0-100>,
  "fomo_potential": "<Low, Medium, or High>",
  "reasoning": "<1 sentence explaining the financial impact of this code change>",
  "action": "<SNIPE, MONITOR, or IGNORE>"
}"""

async def _query_groq(system_prompt: str, user_message: str):
    groq_api_key = os.environ.get("GROQ_API_KEY")
    if not groq_api_key:
        return {"action": "IGNORE", "reasoning": "Missing API Key", "narrative_score": 0, "fomo_potential": "Low"}

    headers = {
        "Authorization": f"Bearer {groq_api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "llama3-70b-8192", 
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ],
        "temperature": 0.1,
        "response_format": {"type": "json_object"}
    }
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(GROQ_API_URL, headers=headers, json=payload, timeout=15.0)
            response.raise_for_status()
            ai_response_text = response.json()['choices'][0]['message']['content']
            return json.loads(ai_response_text)
        except Exception as e:
            print(f"Error querying Groq AI: {e}")
            return {"action": "IGNORE", "reasoning": f"API Error", "narrative_score": 0, "fomo_potential": "Low"}

async def analyze_alpha_event(event_title: str, event_description: str):
    user_message = f"Event Title: {event_title}\nEvent Details: {event_description}"
    return await _query_groq(SYSTEM_PROMPT_GOVERNANCE, user_message)

async def analyze_code_commit(repo_name: str, commit_message: str, patch_diff: str):
    user_message = f"Repository: {repo_name}\nCommit Message: {commit_message}\nCode Changes: {patch_diff}"
    return await _query_groq(SYSTEM_PROMPT_CODE, user_message)
