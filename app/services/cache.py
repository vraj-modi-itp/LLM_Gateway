import uuid
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue
from sentence_transformers import SentenceTransformer

class SemanticCacheService:
    def __init__(self):
        self.qdrant_client = None
        self.embedding_model = None
        self.collection_name = "llm_cache"

    def initialize(self):
        """Safely initializes heavy resources after the process has fully spawned."""
        if self.qdrant_client is None:
            self.qdrant_client = QdrantClient(host="localhost", port=6333)
            self._ensure_collection_exists()
            
        if self.embedding_model is None:
            model_path = "./data/models/all-MiniLM-L6-v2"
            self.embedding_model = SentenceTransformer(model_path)

    def _ensure_collection_exists(self):
        collections = self.qdrant_client.get_collections().collections
        exists = any(c.name == self.collection_name for c in collections)
        if not exists:
            self.qdrant_client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=384, distance=Distance.COSINE),
            )

    def _extract_user_prompt(self, messages) -> str:
        for msg in reversed(messages):
            if msg.role == "user":
                return msg.content
        return ""

    def query_cache(self, messages, threshold: float = 0.90, session_id: str = None):
        # Guard clause in case it's called before initialization completes
        if not self.embedding_model or not self.qdrant_client:
            return None
            
        user_prompt = self._extract_user_prompt(messages)
        if not user_prompt:
            return None

        query_vector = self.embedding_model.encode(user_prompt).tolist()
        
        # --- THE FIX: SESSION ISOLATION FILTER ---
        # If a session_id is provided, block Qdrant from matching any records that share that same ID
        query_filter = None
        if session_id:
            query_filter = Filter(
                must_not=[
                    FieldCondition(
                        key="session_id",
                        match=MatchValue(value=session_id)
                    )
                ]
            )
        
        search_results = self.qdrant_client.query_points(
            collection_name=self.collection_name,
            query=query_vector,
            query_filter=query_filter,
            limit=1
        ).points

        if search_results and search_results[0].score >= threshold:
            return search_results[0].payload.get("response_text")
        return None

    def update_cache(self, messages, response_text: str, session_id: str = None):
        if not self.embedding_model or not self.qdrant_client:
            return

        user_prompt = self._extract_user_prompt(messages)
        if not user_prompt:
            return

        query_vector = self.embedding_model.encode(user_prompt).tolist()
        point_id = str(uuid.uuid4())

        # Save the session_id directly into Qdrant's payload so it can be filtered later
        self.qdrant_client.upsert(
            collection_name=self.collection_name,
            points=[
                PointStruct(
                    id=point_id,
                    vector=query_vector,
                    payload={
                        "prompt_text": user_prompt,
                        "response_text": response_text,
                        "session_id": session_id 
                    }
                )
            ]
        )

# Create the object container shell, but DO NOT load the model weights yet
semantic_cache = SemanticCacheService()