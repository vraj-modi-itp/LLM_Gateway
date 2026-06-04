import httpx
import re
from typing import Tuple, List
from app.core.config import settings

APP_CONTEXTS = {
    "qa-stress-test-v3": "You are a precise technical testing assistant. Output direct, highly specific answers without conversational filler.",
    "app_support_bot": "You are assisting a technical support team. Be specific, cite exact steps, and use bullet points.",
    "sales_assistant": "You are an expert sales strategist. Maintain a professional, persuasive tone and focus on value propositions.",
    "default": "You are a highly capable enterprise AI. Please structure your response clearly and focus on actionable insights."
}

class PromptIntelligenceEngine:
    def __init__(self):
        self.ollama_url = settings.OLLAMA_BASE_URL
        if not self.ollama_url.endswith("/chat/completions") and not self.ollama_url.endswith("/api/chat"):
            self.ollama_url = self.ollama_url.rstrip("/") + "/v1/chat/completions"
            
        self.model = settings.OLLAMA_MODEL

    async def _call_ollama(self, system_prompt: str, user_prompt: str) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.0, 
            "stream": False 
        }
        
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(self.ollama_url, json=payload)
                if response.status_code == 200:
                    data = response.json()
                    if "choices" in data and len(data["choices"]) > 0:
                        return data["choices"][0].get("message", {}).get("content", "").strip()
                    elif "message" in data:
                        return data.get("message", {}).get("content", "").strip()
                else:
                    print(f"Ollama API Error {response.status_code}: {response.text}")
        except Exception as e:
            print(f"Ollama local intelligence failed: {e}")
        return ""

    async def analyze_and_enhance(self, prompt: str, app_id: str) -> Tuple[str, str, bool, List[str]]:
        if not prompt or prompt.isspace():
            return "INSUFFICIENT", prompt, False, ["Empty Prompt"]

        # ---------------------------------------------------------
        # PHASE 1: THE JUDGE (Strict Boundary Rules for 2B Models)
        # ---------------------------------------------------------
        judge_sys_prompt = (
            "You are a strict technical prompt classification engine. Classify the user's prompt into exactly one of these three categories: INSUFFICIENT, NEEDS_CONTEXT, or OPTIMAL.\n"
            "CRITICAL: DO NOT answer the prompt. Output ONLY the category word.\n\n"
            "RULES FOR CLASSIFICATION:\n"
            "1. INSUFFICIENT: Junk text, repetitive spam, or completely vague commands lacking any clear topic or task. Examples: 'do it fast', 'help me', 'apple apple'.\n"
            "2. NEEDS_CONTEXT: A basic, casual task request (e.g., 'write an email', 'create a script', 'fix this code') that lacks explicit architectural constraints, error handling instructions, or deep technical specifications. Most short, simple requests belong here.\n"
            "3. OPTIMAL: A highly detailed, professional prompt that explicitly lists frameworks, strict constraints, specific data structures, or step-by-step logic. It needs zero improvement.\n\n"
            "FEW-SHOT EXAMPLES:\n"
            "Prompt: \"build me something cool i need it fast\" -> CATEGORY: INSUFFICIENT\n"
            "Prompt: \"apple apple apple\" -> CATEGORY: INSUFFICIENT\n"
            "Prompt: \"email the report to ceo@intuitive.ai and make sure it looks good\" -> CATEGORY: NEEDS_CONTEXT\n"
            "Prompt: \"create a python script for a simple calculator\" -> CATEGORY: NEEDS_CONTEXT\n"
            "Prompt: \"Write a SQL query joining the users and orders tables. Group by user_id and return only users with more than 5 orders.\" -> CATEGORY: OPTIMAL\n"
            "Prompt: \"Write a Python FastAPI endpoint that accepts a POST request with a JSON payload containing 'user_id' and 'email'. Validate the email using Pydantic.\" -> CATEGORY: OPTIMAL\n\n"
            "REQUIRED OUTPUT FORMAT:\n"
            "CATEGORY: <INSUFFICIENT/NEEDS_CONTEXT/OPTIMAL>"
        )
        
        wrapped_scoring_prompt = f"Classify this prompt:\n\n<prompt_to_score>\n{prompt}\n</prompt_to_score>"
        
        raw_category_text = await self._call_ollama(judge_sys_prompt, wrapped_scoring_prompt)
        
        category_match = re.search(r'(INSUFFICIENT|NEEDS_CONTEXT|OPTIMAL)', raw_category_text, re.IGNORECASE)
        if category_match:
            category = category_match.group(1).upper()
        else:
            print(f"Failed to parse category from model output: '{raw_category_text}'. Defaulting to NEEDS_CONTEXT.")
            category = "NEEDS_CONTEXT" 
        
        issues = []
        is_enhanced = False
        final_prompt = prompt

        # If INSUFFICIENT, return immediately without touching the editor stage
        if category == "INSUFFICIENT":
            issues.append(f"Category {category}: Prompt is too vague or repetitive. Forwarding rejected.")
            return category, final_prompt, is_enhanced, issues

        # ---------------------------------------------------------
        # PHASE 2: THE EDITOR (Structural Context Injection)
        # ---------------------------------------------------------
        if category == "NEEDS_CONTEXT":
            is_enhanced = True
            prefix = APP_CONTEXTS.get(app_id, APP_CONTEXTS["default"])
            
            editor_sys_prompt = (
                "You are an expert prompt engineer. Your ONLY job is to take a user's vague request and rewrite it into a highly detailed, explicit instruction for another AI to execute. "
                "CRITICAL INSTRUCTION: DO NOT fulfill the user's request yourself! (e.g., Do NOT write the actual email, do NOT write the code). "
                "ONLY output the improved prompt. Make the prompt specific, structured, and professional."
            )
            
            wrapped_editing_prompt = f"Rewrite this vague request into a highly specific prompt for an AI:\n\n<vague_request>\n{prompt}\n</vague_request>"
            
            enhanced_text = await self._call_ollama(editor_sys_prompt, wrapped_editing_prompt)
            
            if enhanced_text:
                # Clean up typical SLM conversational filler
                clean_enhanced_text = re.sub(r'^(here is.*?:|sure.*?:\n|<improved_prompt>|<\/improved_prompt>)', '', enhanced_text, flags=re.IGNORECASE).strip()
                
                # STRUCTURAL INJECTION: We bind the app context here in Python so the main LLM acts perfectly as the persona
                final_prompt = f"System Context / Persona: {prefix}\n\nTask:\n{clean_enhanced_text}"
                
                issues.append(f"Category {category}: Prompt expanded by local SLM and structurally injected with '{app_id}' context.")
            else:
                final_prompt = f"System Context / Persona: {prefix}\n\nTask:\n{prompt}"
                issues.append(f"Category {category}: Model timed out. Fallback static injection applied.")

        elif category == "OPTIMAL":
            issues.append(f"Category {category}: Prompt is already perfect. Passed as-is to main LLM.")

        return category, final_prompt, is_enhanced, issues

prompt_analyzer = PromptIntelligenceEngine()