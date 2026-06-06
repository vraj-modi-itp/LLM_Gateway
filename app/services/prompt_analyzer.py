import asyncio
import re
import json
import httpx
import asyncpg
import ahocorasick
import numpy as np
from typing import Tuple, List
from app.core.config import settings
from app.services.cache import semantic_cache
from app.services.telemetry import DB_DSN

class PromptIntelligenceEngine:
    def __init__(self):
        self.ollama_url = settings.OLLAMA_BASE_URL
        if not self.ollama_url.endswith("/chat/completions") and not self.ollama_url.endswith("/api/chat"):
            self.ollama_url = self.ollama_url.rstrip("/") + "/v1/chat/completions"
            
        self.model = settings.OLLAMA_MODEL
        
        # Fast-Lane Architecture Components
        self.prime_centroid = None
        self.draft_centroid = None
        self.blacklist_automaton = ahocorasick.Automaton()
        self.automaton_built = False
        
        # Slow-Lane Architecture Components
        self.background_queue = asyncio.Queue()

    async def initialize(self):
        """Called once at startup to load the blacklist and calculate vector centroids."""
        print("🧠 Initializing Prompt Intelligence (Centroids & Aho-Corasick)...")
        
        # 1. Load Blacklist and Build Automaton
        await self._rebuild_automaton()

        # 2. Calculate Centroids using the shared SentenceTransformer model
        prime_examples = [
            "Write a multi-tenant Java Spring Boot adapter interface for a scalable B2B SaaS platform. Include explicit connection pooling limits, JWT validation filters, and a PostgreSQL schema migration strategy using Supabase.",
            "Write a SQL query to join the users and orders tables where order_total > 100. Group by user_id and optimize for Postgres 15.",
            "Design an AWS Cloud Infrastructure Visualization architecture with strict IAM OIDC security protocols."
        ]
        
        draft_examples = [
            "do it fast",
            "write an email to the team",
            "make a python script for a calculator",
            "fix my code",
            "apple apple apple"
        ]

        prime_embeddings = semantic_cache.embedding_model.encode(prime_examples)
        draft_embeddings = semantic_cache.embedding_model.encode(draft_examples)

        self.prime_centroid = np.mean(prime_embeddings, axis=0)
        self.draft_centroid = np.mean(draft_embeddings, axis=0)

    async def _rebuild_automaton(self):
        """Fetches the latest blacklist from Postgres and builds the O(n) search tree."""
        try:
            conn = await asyncpg.connect(DB_DSN)
            rows = await conn.fetch("SELECT original_word, mask_tag FROM dynamic_blacklist")
            await conn.close()

            new_automaton = ahocorasick.Automaton()
            for row in rows:
                new_automaton.add_word(row['original_word'], (row['original_word'], row['mask_tag']))
            
            if rows:
                new_automaton.make_automaton()
                self.automaton_built = True
            else:
                self.automaton_built = False
                
            self.blacklist_automaton = new_automaton
            print(f"🔒 Aho-Corasick Automaton rebuilt with {len(rows)} blacklisted terms.")
        except Exception as e:
            print(f"Failed to rebuild blacklist automaton: {e}")

    def _mask_runtime_text(self, text: str) -> Tuple[str, bool]:
        """Instantly masks text using the Aho-Corasick tree without slow loops."""
        if not self.automaton_built:
            return text, False

        matches = []
        for end_idx, (original_word, mask_tag) in self.blacklist_automaton.iter(text):
            start_idx = end_idx - len(original_word) + 1
            matches.append((start_idx, end_idx, original_word, mask_tag))

        if not matches:
            return text, False

        matches.sort(key=lambda x: x[0], reverse=True)
        
        masked_text = text
        for start_idx, end_idx, original_word, mask_tag in matches:
            masked_text = masked_text[:start_idx] + mask_tag + masked_text[end_idx + 1:]

        return masked_text, True

    def _cosine_similarity(self, v1: np.ndarray, v2: np.ndarray) -> float:
        return np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2))

    async def analyze_and_enhance(self, prompt: str, app_id: str) -> Tuple[str, str, bool, List[str]]:
        """THE FAST LANE: Runs in < 10ms."""
        if not prompt or prompt.isspace():
            return "DRAFT", prompt, False, ["Empty Prompt"]

        masked_prompt, was_masked = self._mask_runtime_text(prompt)
        issues = ["Runtime Masking Applied"] if was_masked else []

        prompt_vector = semantic_cache.embedding_model.encode(masked_prompt)
        
        prime_score = self._cosine_similarity(prompt_vector, self.prime_centroid)
        draft_score = self._cosine_similarity(prompt_vector, self.draft_centroid)

        category = "PRIME" if prime_score >= draft_score else "DRAFT"

        self.background_queue.put_nowait({
            "original_prompt": prompt,
            "category": category,
            "app_id": app_id
        })

        return category, masked_prompt, False, issues

    # ---------------------------------------------------------
    # THE SLOW LANE: Asynchronous Background Workers
    # ---------------------------------------------------------
    
    async def background_worker_loop(self):
        print("⚙️ Started Prompt Intelligence Background Worker...")
        while True:
            task = await self.background_queue.get()
            try:
                await self._process_background_task(task)
            except Exception as e:
                print(f"Background task failed: {e}")
            finally:
                self.background_queue.task_done()

    async def _process_background_task(self, task: dict):
        original_prompt = task["original_prompt"]
        category = task["category"]
        
        await self._discover_new_entities(original_prompt)

        if category == "DRAFT":
            await self._generate_and_save_enhancement(original_prompt, task["app_id"])

    async def _discover_new_entities(self, prompt: str):
        sys_prompt = (
            "You are a strict data extraction AI. Your ONLY job is to extract specific proper nouns, "
            "human names, or sensitive company/project names from the provided text. "
            "Output ONLY a valid JSON list of strings. Do not answer the question. Do not apologize. "
            "Example: [\"CyberdyneSystems\", \"Vishnu\", \"Intuitive.AI\"]"
        )
        wrapped_prompt = f"Extract entities from the following text:\n\n<text>\n{prompt}\n</text>"
        
        print(f"🕵️ [Background Worker] Asking Ollama to find entities...")
        response_text = await self._call_ollama(sys_prompt, wrapped_prompt)
        print(f"🤖 [Ollama Raw Output]: '{response_text}'")
        
        if not response_text:
            return

        try:
            clean_json = re.sub(r'```json|```', '', response_text).strip()
            new_entities = json.loads(clean_json)
            
            if new_entities and isinstance(new_entities, list):
                conn = await asyncpg.connect(DB_DSN)
                added_count = 0
                for entity in new_entities:
                    if len(entity) > 2:
                        result = await conn.execute(
                            "INSERT INTO dynamic_blacklist (original_word, mask_tag) VALUES ($1, $2) ON CONFLICT DO NOTHING",
                            entity, f"[REDACTED_{entity[:2].upper()}]"
                        )
                        if result == "INSERT 0 1":
                            added_count += 1
                await conn.close()
                
                if added_count > 0:
                    await self._rebuild_automaton()
        except json.JSONDecodeError:
            print(f"❌ [Background Worker] Failed to parse JSON.")
        except Exception:
            pass

    async def _generate_and_save_enhancement(self, prompt: str, app_id: str):
        """Generates an optimal prompt and UPDATES the existing fast-lane telemetry log."""
        sys_prompt = (
            "You are an expert prompt engineer. Rewrite this vague request into a highly specific, "
            "professional instruction for an AI. Output ONLY the improved prompt."
        )
        
        enhanced_prompt = await self._call_ollama(sys_prompt, prompt)
        if enhanced_prompt:
            try:
                conn = await asyncpg.connect(DB_DSN)
                # FIX: We use UPDATE to merge this exactly with the row the Fast Lane already created!
                await conn.execute(
                    """
                    UPDATE prompt_quality_scores 
                    SET enhanced_prompt = $2, 
                        is_enhanced = TRUE, 
                        detected_issues = array_append(COALESCE(detected_issues, ARRAY[]::text[]), 'Background Suggested Enhancement')
                    WHERE original_prompt = $1 AND category = 'DRAFT'
                    """,
                    prompt, enhanced_prompt
                )
                await conn.close()
                print("✅ [Background Worker] Successfully updated DRAFT prompt in dashboard!")
            except Exception as e:
                print(f"❌ Failed to log enhancement to DB: {e}")

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
                    return response.json()["choices"][0].get("message", {}).get("content", "").strip()
        except Exception:
            pass
        return ""

prompt_analyzer = PromptIntelligenceEngine()