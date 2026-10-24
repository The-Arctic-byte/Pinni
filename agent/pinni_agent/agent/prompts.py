"""Structured JSON schemas and prompts for Ollama / Qwen 3.5 quantized models."""
from typing import Any, Dict

SELECT_CLASSIFICATION_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "required": ["category", "scale", "needs", "risk", "drop", "dropReason", "tags"],
    "properties": {
        "category": {
            "type": "string",
            "enum": [
                "economy", "society", "politics", "shopping", "sport", "safety",
                "culture", "transport", "education", "housing", "health", "work",
                "environment", "technology", "world", "cityLife"
            ],
        },
        "scale": {
            "type": "string",
            "enum": ["area", "city", "finland", "world"],
        },
        "needs": {
            "type": "array",
            "items": {
                "type": "string",
                "enum": ["safety", "information", "understanding", "usefulness", "community", "emotion"],
            },
        },
        "risk": {
            "type": "string",
            "enum": ["none", "amber", "red"],
        },
        "drop": {"type": "boolean"},
        "dropReason": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string"}},
    },
}

EXPLANATION_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "required": ["known", "happened", "notKnown", "forYou", "contextQuestion", "contextAnswer"],
    "properties": {
        "known": {"type": "array", "items": {"type": "string"}},
        "happened": {"type": "string"},
        "notKnown": {"type": "string"},
        "forYou": {"type": "string"},
        "contextQuestion": {"type": "string"},
        "contextAnswer": {"type": "string"},
    },
}

TRANSLATION_CHECK_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "required": ["translated_title", "translated_for_you", "back_translation", "discrepancy_score", "tier"],
    "properties": {
        "translated_title": {"type": "string"},
        "translated_for_you": {"type": "string"},
        "back_translation": {"type": "string"},
        "discrepancy_score": {"type": "number"},
        "tier": {"type": "integer", "enum": [1, 2, 3]},
    },
}


def build_select_prompt(title: str, text: str, source: str) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "You are the Pinni news selection and classification supervisor. "
                "Classify this incoming news article into valid category, scale, need, and risk. "
                "If it is promotional spam or out of scope for Oulu residents, set drop=true and provide dropReason."
            ),
        },
        {
            "role": "user",
            "content": f"Source: {source}\nTitle: {title}\nText: {text}",
        },
    ]


def build_explanation_prompt(title: str, text: str, category: str, place: str) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "You are the Pinni news explainer for international and local residents in Oulu. "
                "Write clear, bite-sized explanation sections: 'known' (bullet facts), 'happened' (summary), "
                "'notKnown' (what authorities haven't confirmed yet), 'forYou' (practical impact for reader), "
                "and a helpful Q&A context card."
            ),
        },
        {
            "role": "user",
            "content": f"Place: {place}\nCategory: {category}\nTitle: {title}\nBody: {text}",
        },
    ]


def build_translation_prompt(text: str, target_lang: str) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                f"You are a translation and verification agent translating into {target_lang}. "
                "Translate the title and forYou note, back-translate to English to verify accuracy, "
                "and compute discrepancy score between 0.0 (exact) and 1.0 (drift)."
            ),
        },
        {
            "role": "user",
            "content": f"Text to translate into {target_lang}:\n{text}",
        },
    ]
