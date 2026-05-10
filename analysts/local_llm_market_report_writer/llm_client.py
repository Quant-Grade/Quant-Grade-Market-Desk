import os
import json
import urllib.request
import urllib.error
from typing import Dict, Any

from .schemas import LLMResponseError

def query_local_llm(system_prompt: str, user_prompt: str) -> str:
    """Queries the local LLM using OpenAI's Chat Completions schema over urllib."""
    
    base_url = os.environ.get("LOCAL_LLM_BASE_URL", "http://localhost:1234/v1")
    model = os.environ.get("LOCAL_LLM_MODEL", "local-model")
    
    endpoint = f"{base_url}/chat/completions"
    
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.2
    }
    
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(endpoint, data=data, headers={"Content-Type": "application/json"})
    
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            result = json.loads(response.read().decode("utf-8"))
            content = result["choices"][0]["message"]["content"].strip()
            
            # Clean Deepseek / LM Studio reasoning tags
            if "<channel|>" in content:
                content = content.split("<channel|>")[-1].strip()
            if "</think>" in content:
                content = content.split("</think>")[-1].strip()
                
            # Clean markdown JSON formatting
            if content.startswith("```json"):
                content = content[7:].strip()
            elif content.startswith("```"):
                content = content[3:].strip()
                
            if content.endswith("```"):
                content = content[:-3].strip()
                
            return content
    except urllib.error.URLError as e:
        raise LLMResponseError(f"Failed to connect to local LLM at {endpoint}: {e}")
    except KeyError as e:
        raise LLMResponseError(f"Unexpected response format from LLM: missing {e}")
    except Exception as e:
        raise LLMResponseError(f"Error querying LLM: {e}")
