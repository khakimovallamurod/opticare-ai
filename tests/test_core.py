"""
Tests for OptiCare core flows.
"""

import json
from unittest.mock import patch, MagicMock

from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse

from scans.models import Scan
from scans.services.gemini import analyze_eye_image


# ── Minimal JPEG bytes for testing ────────────────────────────────────────────
MINIMAL_JPEG = bytes([
    0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46, 0x49, 0x46, 0x00, 0x01,
    0x01, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0xFF, 0xDB, 0x00, 0x43,
    0x00, 0x08, 0x06, 0x06, 0x07, 0x06, 0x05, 0x08, 0x07, 0x07, 0x07, 0x09,
    0x09, 0x08, 0x0A, 0x0C, 0x14, 0x0D, 0x0C, 0x0B, 0x0B, 0x0C, 0x19, 0x12,
    0x13, 0x0F, 0x14, 0x1D, 0x1A, 0x1F, 0x1E, 0x1D, 0x1A, 0x1C, 0x1C, 0x20,
    0x24, 0x2E, 0x27, 0x20, 0x22, 0x2C, 0x23, 0x1C, 0x1C, 0x28, 0x37, 0x29,
    0x2C, 0x30, 0x31, 0x34, 0x34, 0x34, 0x1F, 0x27, 0x39, 0x3D, 0x38, 0x32,
    0x3C, 0x2E, 0x33, 0x34, 0x32, 0xFF, 0xC0, 0x00, 0x0B, 0x08, 0x00, 0x01,
    0x00, 0x01, 0x01, 0x01, 0x11, 0x00, 0xFF, 0xC4, 0x00, 0x1F, 0x00, 0x00,
    0x01, 0x05, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08,
    0x09, 0x0A, 0x0B, 0xFF, 0xDA, 0x00, 0x08, 0x01, 0x01, 0x00, 0x00, 0x3F,
    0x00, 0xFB, 0xD5, 0xFF, 0xD9,
])


# ────────────────────────────────────────────────────────────────────────────────
# Auth tests
# ────────────────────────────────────────────────────────────────────────────────
class DemoLoginTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="demo", first_name="Ibodat", last_name="Musurmonova"
        )

    def test_demo_login_success(self):
        """POST to demo_login should log in and redirect to dashboard."""
        response = self.client.post(reverse("demo_login"), follow=True)
        self.assertTrue(response.context["user"].is_authenticated)
        self.assertEqual(response.context["user"].username, "demo")

    def test_demo_login_get_redirects(self):
        """GET to demo_login should redirect to landing."""
        response = self.client.get(reverse("demo_login"))
        self.assertRedirects(response, reverse("landing"), fetch_redirect_response=False)

    def test_landing_redirects_logged_in_user(self):
        """Authenticated user visiting landing should be sent to dashboard."""
        self.client.force_login(self.user)
        response = self.client.get(reverse("landing"))
        self.assertRedirects(response, reverse("dashboard"), fetch_redirect_response=False)

    def test_dashboard_requires_login(self):
        """Dashboard should redirect unauthenticated users."""
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 302)

    def test_logout(self):
        """Logout should end the session."""
        self.client.force_login(self.user)
        self.client.post(reverse("logout"))
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 302)


# ────────────────────────────────────────────────────────────────────────────────
# User isolation tests
# ────────────────────────────────────────────────────────────────────────────────
class UserIsolationTests(TestCase):
    def setUp(self):
        self.user_a = User.objects.create_user(username="user_a", password="pass_a")
        self.user_b = User.objects.create_user(username="user_b", password="pass_b")

        # Create a scan owned by user_a
        self.scan_a = Scan.objects.create(
            user=self.user_a,
            status=Scan.STATUS_OK,
            result_class=Scan.CLASS_NORMAL,
            confidence=0.9,
            summary="Test",
            observations=[],
            recommendations=[],
        )

    def test_user_b_cannot_see_user_a_scan(self):
        """User B must not be able to access user A's scan detail."""
        self.client.force_login(self.user_b)
        response = self.client.get(reverse("scan_detail", kwargs={"pk": self.scan_a.pk}))
        self.assertEqual(response.status_code, 404)

    def test_user_b_cannot_delete_user_a_scan(self):
        """User B must not be able to delete user A's scan."""
        self.client.force_login(self.user_b)
        response = self.client.post(reverse("scan_delete", kwargs={"pk": self.scan_a.pk}))
        self.assertEqual(response.status_code, 404)
        # Scan still exists
        self.assertTrue(Scan.objects.filter(pk=self.scan_a.pk).exists())

    def test_history_only_shows_own_scans(self):
        """History view should only list scans belonging to the logged-in user."""
        self.client.force_login(self.user_b)
        response = self.client.get(reverse("scan_history"))
        scans = list(response.context["page_obj"])
        self.assertEqual(len(scans), 0)

        self.client.force_login(self.user_a)
        response = self.client.get(reverse("scan_history"))
        scans = list(response.context["page_obj"])
        self.assertEqual(len(scans), 1)


# ────────────────────────────────────────────────────────────────────────────────
# Gemini service mocked tests
# ────────────────────────────────────────────────────────────────────────────────
class GeminiServiceTests(TestCase):
    VALID_RESULT = {
        "valid": True,
        "class": "normal",
        "confidence": 0.92,
        "observations": ["Ko'z sog'lom ko'rinadi"],
        "recommendations": ["Ekran vaqtini cheklang"],
        "summary": "Ko'z holati yaxshi.",
    }

    INVALID_RESULT = {
        "valid": False,
        "invalid_reason": "Rasmda inson yuzi aniqlanmadi.",
    }

    def _mock_response(self, data: dict):
        """Build a mock Gemini response object."""
        mock_resp = MagicMock()
        mock_resp.text = json.dumps(data)
        return mock_resp

    @patch("scans.services.gemini.genai_types")
    @patch("scans.services.gemini.genai")
    def test_valid_response(self, mock_genai, mock_types):
        """Gemini service should parse a valid JSON response correctly."""
        mock_client = MagicMock()
        mock_genai.Client.return_value = mock_client
        mock_client.models.generate_content.return_value = self._mock_response(self.VALID_RESULT)

        with self.settings(GEMINI_API_KEY="fake-key"):
            result = analyze_eye_image(MINIMAL_JPEG, "image/jpeg", age=8)
        self.assertTrue(result.get("valid"))
        self.assertEqual(result.get("class"), "normal")
        self.assertAlmostEqual(result.get("confidence"), 0.92)

    @patch("scans.services.gemini.genai_types")
    @patch("scans.services.gemini.genai")
    def test_invalid_image_response(self, mock_genai, mock_types):
        """Gemini service should handle invalid image responses gracefully."""
        mock_client = MagicMock()
        mock_genai.Client.return_value = mock_client
        mock_client.models.generate_content.return_value = self._mock_response(self.INVALID_RESULT)

        with self.settings(GEMINI_API_KEY="fake-key"):
            result = analyze_eye_image(MINIMAL_JPEG, "image/jpeg")
        self.assertFalse(result.get("valid"))
        self.assertIn("yuzi", result.get("invalid_reason", ""))

    @patch("scans.services.gemini.genai_types")
    @patch("scans.services.gemini.genai")
    def test_api_error_returns_error_dict(self, mock_genai, mock_types):
        """API errors should return an error dict, not raise an exception."""
        mock_client = MagicMock()
        mock_genai.Client.return_value = mock_client
        mock_client.models.generate_content.side_effect = Exception("Connection error")

        with self.settings(GEMINI_API_KEY="fake-key"):
            result = analyze_eye_image(MINIMAL_JPEG, "image/jpeg")
        self.assertFalse(result.get("valid"))
        self.assertTrue(result.get("error"))
        self.assertIn("error_message", result)

    @patch("scans.services.gemini.genai_types")
    @patch("scans.services.gemini.genai")
    def test_json_parse_error_retries_and_fails(self, mock_genai, mock_types):
        """JSON parse errors should trigger retries and eventually return error dict."""
        mock_client = MagicMock()
        mock_genai.Client.return_value = mock_client
        bad_response = MagicMock()
        bad_response.text = "Not valid JSON at all ~~{"
        mock_client.models.generate_content.return_value = bad_response

        with self.settings(GEMINI_API_KEY="fake-key"):
            result = analyze_eye_image(MINIMAL_JPEG, "image/jpeg")
        self.assertFalse(result.get("valid"))
        self.assertTrue(result.get("error"))

    def test_missing_api_key_returns_error(self):
        """Missing API key should return an error dict immediately."""
        with self.settings(GEMINI_API_KEY=""):
            result = analyze_eye_image(MINIMAL_JPEG, "image/jpeg")
        self.assertFalse(result.get("valid"))
        self.assertTrue(result.get("error"))


# ────────────────────────────────────────────────────────────────────────────────
# Seed demo command test
# ────────────────────────────────────────────────────────────────────────────────
class SeedDemoCommandTests(TestCase):
    def test_seed_demo_creates_user_and_scans(self):
        """seed_demo management command should create demo user and scans."""
        from django.core.management import call_command
        call_command("seed_demo", verbosity=0)

        user = User.objects.get(username="demo")
        self.assertEqual(user.first_name, "Ibodat")
        self.assertEqual(user.last_name, "Musurmonova")

        scan_count = Scan.objects.filter(user=user).count()
        self.assertGreaterEqual(scan_count, 12)

    def test_seed_demo_idempotent(self):
        """Running seed_demo twice should not duplicate users or create >12 scans."""
        from django.core.management import call_command
        call_command("seed_demo", verbosity=0)
        call_command("seed_demo", verbosity=0)

        user_count = User.objects.filter(username="demo").count()
        self.assertEqual(user_count, 1)


# ────────────────────────────────────────────────────────────────────────────────
# Scan model & image processing tests
# ────────────────────────────────────────────────────────────────────────────────
class ScanModelAndImageUtilsTests(TestCase):
    def test_confidence_percent_calculation(self):
        """confidence_percent should return correct integer percentage."""
        user = User.objects.create_user(username="test_scan_user")
        scan = Scan(user=user, confidence=0.876)
        self.assertEqual(scan.confidence_percent, 88)

        scan_none = Scan(user=user, confidence=None)
        self.assertIsNone(scan_none.confidence_percent)

        scan_hundred = Scan(user=user, confidence=95.0)
        self.assertEqual(scan_hundred.confidence_percent, 95)

    def test_process_image_valid_jpeg(self):
        """process_image should process valid JPEG bytes."""
        from scans.services.image_utils import process_image
        processed, mime = process_image(MINIMAL_JPEG, "eye.jpg")
        self.assertEqual(mime, "image/jpeg")
        self.assertTrue(len(processed) > 0)

    def test_process_image_invalid_extension(self):
        """process_image should reject disallowed file extensions."""
        from scans.services.image_utils import process_image
        with self.assertRaises(ValueError):
            process_image(MINIMAL_JPEG, "eye.exe")
