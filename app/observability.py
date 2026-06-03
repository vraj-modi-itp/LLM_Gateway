import os
from dotenv import load_dotenv
from phoenix.otel import register
from opentelemetry import trace

# Force load the local .env file before Phoenix boots up
load_dotenv()

def init_observability():
    """
    Initializes Arize Phoenix Cloud tracing using the official SDK pattern.
    """
    # Ensure quotes are stripped just in case they were left in the .env file
    if "PHOENIX_API_KEY" in os.environ:
        os.environ["PHOENIX_API_KEY"] = os.environ["PHOENIX_API_KEY"].strip("'\"")
    if "PHOENIX_COLLECTOR_ENDPOINT" in os.environ:
        os.environ["PHOENIX_COLLECTOR_ENDPOINT"] = os.environ["PHOENIX_COLLECTOR_ENDPOINT"].strip("'\"")

    if not os.getenv("PHOENIX_API_KEY"):
        print("⚠️ Phoenix API Key missing. Tracing disabled.")
        return

    # Official Phoenix implementation - it will natively parse the /s/rahuljmorabiya URL
    tracer_provider = register(
        project_name="Biweekly_project"
    )
    
    trace.set_tracer_provider(tracer_provider)
    print("🚀 Arize Phoenix Cloud tracing initialized via official SDK")

def get_tracer():
    """Returns the global tracer instance for manual span creation."""
    return trace.get_tracer("ai-proxy-gateway")