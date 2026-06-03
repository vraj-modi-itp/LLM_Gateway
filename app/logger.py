import sys
import json
import logging
from datetime import datetime, timezone
from opentelemetry import trace

class JsonFormatter(logging.Formatter):
    """
    Custom formatter to output system events as structured JSON.
    """
    def format(self, record):
        # Extract OpenTelemetry tracking context if available
        current_span = trace.get_current_span()
        context = current_span.get_span_context()
        
        trace_id = format(context.trace_id, "032x") if context.is_valid else None
        span_id = format(context.span_id, "016x") if context.is_valid else None

        log_record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
        }

        # Inject tracing details for 1:1 correlation with Arize Phoenix
        if trace_id:
            log_record["trace_id"] = trace_id
            log_record["span_id"] = span_id

        # Safely inject extra context parameters passed via logging.info(..., extra={})
        if hasattr(record, "extra_fields"):
            log_record.update(record.extra_fields)
        elif isinstance(getattr(record, "args", None), dict):
            log_record.update(record.args)

        return json.dumps(log_record)

def setup_logging():
    """
    Configures the root logger to use the structured JSON formatter.
    """
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    # Remove existing handlers to avoid duplicate text logs
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    
    # Suppress verbose noisy libraries to keep the JSON stream clean
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)

# Initialize standard gateway logger export
gateway_log = logging.getLogger("gateway")