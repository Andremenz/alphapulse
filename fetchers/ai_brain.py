import httpx
import json
import os

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
PROMPTS_FILE = "data/active_prompts.json"

def load_prompts():
    try:
        with open(PROMPTS_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"governance": "", "code": ""}

PROMPTS = load_prompts()

async def _query_groq(system_prompt: str, user_message: str):
    groq_api_key = os.environ.get("GROQ_API_KEY")
    if not groq_api_key:
        return {"action": "IGNORE", "reasoning": "Missing API Key", "narrative_score": 0, "fomo_potential": "Low"}

    headers = {"Authorization": f"Bearer {groq_api_key}", "Content-Type": "application/json"}
    payload = {"model": "llama3-70b-8192", "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_message}], "temperature": 0.1, "response_format": {"type": "json_object"}}
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(GROQ_API_URL, headers=headers, json=payload, timeout=15.0)
            response.raise_for_status()
            return json.loads(response.json()['choices'][0]['message']['content'])
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 400: return {"action": "IGNORE", "reasoning": "Prompt format error", "narrative_score": 0, "fomo_potential": "Low"}
            return {"action": "IGNORE", "reasoning": f"API Error: {e}", "narrative_score": 0, "fomo_potential": "Low"}
        except Exception as e:
            return {"action": "IGNORE", "reasoning": f"API Error", "narrative_score": 0, "fomo_potential": "Low"}

async def analyze_alpha_event(event_title: str, event_description: str):
    user_message = f"Event Title: {event_title}\nEvent Details: {event_description}"
    return await _query_groq(load_prompts().get("governance", ""), user_message)

async def analyze_code_commit(repo_name: str, commit_message: str, patch_diff: str):
    diff_text = patch_diff if patch_diff and len(patch_diff.strip()) > 10 else "No code diff available (commit message only)"
    user_message = f"Repository: {repo_name}\nCommit Message: {commit_message}\nCode Changes: {diff_text}"
    return await _query_groq(load_prompts().get("code", ""), user_message)
