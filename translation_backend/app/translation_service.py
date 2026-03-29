from __future__ import annotations

try:
    from deep_translator import GoogleTranslator
except ImportError:
    GoogleTranslator = None


class TranslationService:
    """
    Translation service using deep-translator (Google Translate free tier).
    No API key required.
    """

    SUPPORTED_LANGUAGES = {"en": "english", "hi": "hindi"}

    def __init__(self):
        if GoogleTranslator is None:
            raise RuntimeError(
                "deep-translator not installed. Run: pip install deep-translator"
            )

    def translate(
        self, text: str, source_language: str = "en", target_language: str = "hi"
    ) -> dict:
        """
        Translate text between supported languages.
        Returns dict with translated_text, languages, and confidence.
        """
        src = source_language.lower()
        tgt = target_language.lower()

        if src not in self.SUPPORTED_LANGUAGES:
            raise ValueError(f"Unsupported source language: {src}")
        if tgt not in self.SUPPORTED_LANGUAGES:
            raise ValueError(f"Unsupported target language: {tgt}")

        if src == tgt:
            # No translation needed
            return {
                "translated_text": text,
                "source_language": src,
                "target_language": tgt,
                "confidence": 1.0,
            }

        try:
            translator = GoogleTranslator(
                source_language=src, target_language=tgt
            )
            translated = translator.translate(text)

            # Confidence is high assuming Google Translate is reliable
            # In production, you might use a language confidence score
            confidence = 0.95

            return {
                "translated_text": translated,
                "source_language": src,
                "target_language": tgt,
                "confidence": confidence,
            }
        except Exception as exc:
            raise ValueError(f"Translation error: {str(exc)}") from exc
