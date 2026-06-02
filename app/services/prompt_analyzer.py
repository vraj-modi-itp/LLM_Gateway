import spacy
from typing import Tuple, List

# Load the same fast small model used by DLP so we don't increase RAM usage
try:
    nlp = spacy.load("en_core_web_sm")
except OSError:
    import subprocess
    import sys
    subprocess.check_call([sys.executable, "-m", "spacy", "download", "en_core_web_sm"])
    nlp = spacy.load("en_core_web_sm")

# Context Injection Dictionary mapped to App IDs
APP_CONTEXTS = {
    "qa-stress-test-v3": "You are a precise technical testing assistant. Output direct, highly specific answers without conversational filler. ",
    "app_support_bot": "You are assisting a technical support team. Be specific, cite exact steps, and use bullet points. ",
    "sales_assistant": "You are an expert sales strategist. Maintain a professional, persuasive tone and focus on value propositions. ",
    "default": "You are a highly capable enterprise AI. Please structure your response clearly and focus on actionable insights. "
}

class PromptIntelligenceEngine:
    def __init__(self, threshold: int = 60):
        self.threshold = threshold

    def analyze_and_enhance(self, prompt: str, app_id: str) -> Tuple[int, str, bool, List[str]]:
        """
        Analyzes the prompt using NLP structural mapping.
        Returns: (score, final_prompt, is_enhanced, detected_issues)
        """
        if not prompt or prompt.isspace():
            return 0, prompt, False, ["Empty Prompt"]

        doc = nlp(prompt)
        total_words = len([token for token in doc if not token.is_punct and not token.is_space])
        
        if total_words == 0:
            return 0, prompt, False, ["No usable words"]

        verbs = len([token for token in doc if token.pos_ == "VERB"])
        nouns = len([token for token in doc if token.pos_ in ["NOUN", "PROPN"]])
        
        score = 0
        issues = []
        is_enhanced = False
        final_prompt = prompt

        # ---------------------------------------------------------
        # EDGE CASE 1: Short but Perfect (High Density)
        # ---------------------------------------------------------
        if total_words < 12 and verbs >= 1 and nouns >= 1:
            score = 95 # Bypasses enhancement because intent is clear and direct
            
        # ---------------------------------------------------------
        # EDGE CASE 2: The Rambling Wall (Low Action Ratio)
        # ---------------------------------------------------------
        elif verbs == 0 and nouns > 8:
            score = 25
            issues.append("Rambling: Missing clear action verbs.")
            
        # ---------------------------------------------------------
        # STANDARD SCORING FORMULA
        # ---------------------------------------------------------
        else:
            action_density = verbs / total_words
            detail_density = nouns / total_words
            
            # Base points for length (up to 40)
            length_score = min(total_words, 40)
            # Density multiplier (Action is heavily weighted)
            action_score = min(action_density * 250, 40)
            detail_score = min(detail_density * 150, 20)
            
            score = int(length_score + action_score + detail_score)
            
            if action_density < 0.05:
                issues.append("Low action clarity.")
            if detail_density < 0.1:
                issues.append("Lacks specific context/nouns.")

        # Hard cap score at 100
        score = min(score, 100)

        # ---------------------------------------------------------
        # ENHANCEMENT INJECTION LOGIC
        # ---------------------------------------------------------
        if score < self.threshold:
            is_enhanced = True
            prefix = APP_CONTEXTS.get(app_id, APP_CONTEXTS["default"])
            
            # We only append behavior rules, preventing factual contradiction
            final_prompt = f"System Instruction: {prefix}\n\nUser Request: {prompt}"

        return score, final_prompt, is_enhanced, issues

prompt_analyzer = PromptIntelligenceEngine(threshold=60)