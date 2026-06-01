from sentence_transformers import SentenceTransformer
import os

MODEL_NAME = "all-MiniLM-L6-v2"
SAVE_PATH = "./data/models/" + MODEL_NAME

print(f"Downloading {MODEL_NAME} (this may take a minute)...")

# This downloads the model into RAM
model = SentenceTransformer(MODEL_NAME)

# This saves it permanently to your local data folder
os.makedirs(SAVE_PATH, exist_ok=True)
model.save(SAVE_PATH)

print(f"Success! Model saved locally to {SAVE_PATH}. Ready for offline use.")