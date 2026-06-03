from presidio_analyzer import AnalyzerEngine
from presidio_analyzer.nlp_engine import NlpEngineProvider
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig
from typing import List, Tuple
from app.api.schemas import ChatMessage

class DLPService:
    def __init__(self):
        configuration = {
            "nlp_engine_name": "spacy",
            "models": [{"lang_code": "en", "model_name": "en_core_web_sm"}],
        }
        provider = NlpEngineProvider(nlp_configuration=configuration)
        nlp_engine = provider.create_engine()

        self.analyzer = AnalyzerEngine(nlp_engine=nlp_engine)
        self.anonymizer = AnonymizerEngine()
        
        self.target_entities = ["EMAIL_ADDRESS", "PHONE_NUMBER", "CREDIT_CARD", "PERSON", "US_SSN"]
        
        # Explicit mapping operators to output [EMAIL], [SSN], etc.
        self.operators = {
            "EMAIL_ADDRESS": OperatorConfig("replace", {"new_value": "[EMAIL]"}),
            "PHONE_NUMBER": OperatorConfig("replace", {"new_value": "[PHONE]"}),
            "CREDIT_CARD": OperatorConfig("replace", {"new_value": "[CREDIT_CARD]"}),
            "PERSON": OperatorConfig("replace", {"new_value": "[PERSON]"}),
            "US_SSN": OperatorConfig("replace", {"new_value": "[SSN]"})
        }

    def scan_and_redact_messages(self, messages: List[ChatMessage]) -> Tuple[List[ChatMessage], List[str], bool]:
        sanitized_messages = []
        detected_entities = set()
        any_redaction_triggered = False

        for msg in messages:
            text_to_scan = msg.content
            
            analysis_results = self.analyzer.analyze(
                text=text_to_scan,
                language="en",
                entities=self.target_entities
            )

            if analysis_results:
                any_redaction_triggered = True
                for result in analysis_results:
                    detected_entities.add(result.entity_type)

                # Inject the operator configurations here
                anonymized_result = self.anonymizer.anonymize(
                    text=text_to_scan,
                    analyzer_results=analysis_results,
                    operators=self.operators
                )
                
                sanitized_messages.append(
                    ChatMessage(role=msg.role, content=anonymized_result.text)
                )
            else:
                sanitized_messages.append(msg)

        return sanitized_messages, list(detected_entities), any_redaction_triggered

    def scan_and_redact_text(self, text: str) -> str:
        """Scans and redacts a raw string. Used for Egress Output Guardrails."""
        if not text:
            return text
            
        analysis_results = self.analyzer.analyze(
            text=text,
            language="en",
            entities=self.target_entities
        )
        
        if analysis_results:
            anonymized_result = self.anonymizer.anonymize(
                text=text,
                analyzer_results=analysis_results,
                operators=self.operators
            )
            return anonymized_result.text
            
        return text

dlp_service = DLPService()