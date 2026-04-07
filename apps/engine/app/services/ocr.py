"""OCR service — extracts raw text from medical bill images and PDFs.

All calls to Google Cloud Vision are funneled through this module.
In test mode, returns fixture data instead of making real API calls.
"""

import json
import logging
from pathlib import Path

from google.cloud import vision
from google.oauth2 import service_account

from app.core.config import settings

logger = logging.getLogger(__name__)


def _build_vision_client() -> vision.ImageAnnotatorClient:
    """Build the Vision client from JSON content or file path.

    Containerised deployments (Railway, Fly.io) pass the full service account
    JSON as GOOGLE_CREDENTIALS_JSON. Local development uses the file path in
    GOOGLE_APPLICATION_CREDENTIALS, which the Google SDK reads automatically.
    """
    if settings.google_credentials_json:
        info = json.loads(settings.google_credentials_json)
        creds = service_account.Credentials.from_service_account_info(
            info, scopes=["https://www.googleapis.com/auth/cloud-vision"]
        )
        return vision.ImageAnnotatorClient(credentials=creds)
    # Fall back to ADC / GOOGLE_APPLICATION_CREDENTIALS file path
    return vision.ImageAnnotatorClient()


class OcrService:
    """Wraps Google Cloud Vision for document text extraction."""

    def __init__(self, test_mode: bool = False) -> None:
        self._test_mode = test_mode
        if not test_mode:
            self._client = _build_vision_client()

    async def extract_text(self, file_bytes: bytes, mime_type: str) -> str:
        """Extract all text from a bill image or PDF.

        Args:
            file_bytes: Raw bytes of the uploaded file.
            mime_type: MIME type — 'application/pdf', 'image/jpeg', or 'image/png'.

        Returns:
            Full text extracted from the document.

        Raises:
            OcrExtractionError: When Vision API fails or returns no text.
        """
        if self._test_mode:
            return self._fixture_text()

        if mime_type == "application/pdf":
            return await self._extract_from_pdf(file_bytes)
        return await self._extract_from_image(file_bytes, mime_type)

    async def _extract_from_image(self, file_bytes: bytes, mime_type: str) -> str:
        image = vision.Image(content=file_bytes)
        response = self._client.document_text_detection(image=image)

        if response.error.message:
            raise OcrExtractionError(f"Google Vision API error: {response.error.message}")

        text = response.full_text_annotation.text
        if not text:
            raise OcrExtractionError("No text detected in the uploaded image.")

        logger.info("OCR extracted %d characters from image", len(text))
        return text

    async def _extract_from_pdf(self, file_bytes: bytes) -> str:
        # PDF processing uses the async batch annotate API
        # For now, treat first-page as image (Phase 2 will handle multi-page PDFs)
        feature = vision.Feature(type_=vision.Feature.Type.DOCUMENT_TEXT_DETECTION)
        image = vision.Image(content=file_bytes)
        request = vision.AnnotateImageRequest(image=image, features=[feature])
        response = self._client.annotate_image(request)

        if response.error.message:
            raise OcrExtractionError(f"Google Vision API error: {response.error.message}")

        text = response.full_text_annotation.text
        if not text:
            raise OcrExtractionError("No text detected in the uploaded PDF.")

        logger.info("OCR extracted %d characters from PDF", len(text))
        return text

    @staticmethod
    def _fixture_text() -> str:
        """Returns realistic fixture text for testing — avoids real API calls."""
        fixture_path = Path(__file__).parent.parent / "data" / "fixtures" / "sample_bill.txt"
        if fixture_path.exists():
            return fixture_path.read_text()
        # Minimal inline fixture when file doesn't exist yet
        return (
            "STATEMENT OF ACCOUNT\n"
            "Patient: John Doe | DOB: 01/15/1970\n"
            "Service Date: 2026-03-15\n"
            "99214  Office Visit, Established Patient  $350.00\n"
            "99214  Office Visit, Established Patient  $350.00\n"
            "85025  Complete Blood Count               $120.00\n"
            "Total: $820.00\n"
        )


class OcrExtractionError(Exception):
    """Raised when OCR fails to extract text from a document."""
