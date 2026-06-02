Made by sm 

first make a virtual environment:
python -m venv .venv

then activate it 
.\.venv\Scripts\Activate
and then 
pip install -r requirements.txt

Also install streamlit and psycopg2 (they are not in requirements.txt)

then make a .env and set api keys for groq and gemini 
GROQ_API_KEY=your_groq_api_token_here
GEMINI_API_KEY=your_gemini_api_token_here
POSTGRES_USER=proxy_user
POSTGRES_PASSWORD=proxy_password
POSTGRES_DB=proxy_db

then run this to get model cached
python app/core/setup_model.py

finally open 3 terminal with venv
uvicorn app.main:app --port 8000 --reload
streamlit run dashboard.py --server.port 8501
streamlit run dashboard.py --server.port 8501

Note: i have postgres locally installed so it interferes with port numbers so i have changes it to 5433 
