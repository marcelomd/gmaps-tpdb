from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import CustomUser


@override_settings(SITE_URL="https://example.test", EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class MagicLinkTests(TestCase):
    def setUp(self):
        cache.clear()
        CustomUser.objects.create_user("known@example.com")

    def post_login(self, email):
        return self.client.post(reverse("login"), {"email": email, "password": ""}, follow=True)

    def test_known_and_unknown_emails_get_the_same_response(self):
        known = self.post_login("known@example.com")
        unknown = self.post_login("unknown@example.com")
        self.assertEqual(
            [str(m) for m in known.context["messages"]],
            [str(m) for m in unknown.context["messages"]],
        )

    @override_settings(ALLOWED_HOSTS=["evil.test"])
    def test_link_uses_configured_site_url_not_host_header(self):
        self.client.post(reverse("login"), {"email": "known@example.com", "password": ""}, HTTP_HOST="evil.test")
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("https://example.test/?sesame=", mail.outbox[0].body)
        self.assertNotIn("evil.test", mail.outbox[0].body)

    def test_second_request_within_cooldown_sends_nothing(self):
        self.post_login("known@example.com")
        self.post_login("Known@Example.com")
        self.assertEqual(len(mail.outbox), 1)

    def test_send_failure_looks_like_success(self):
        with override_settings(EMAIL_BACKEND="tests.does.not.exist"):
            response = self.post_login("known@example.com")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("error", " ".join(str(m) for m in response.context["messages"]).lower())

    def test_magic_link_logs_user_in(self):
        self.post_login("known@example.com")
        link = mail.outbox[0].body.split("log in: ")[1].split()[0]
        self.client.get(link.replace("https://example.test", ""))
        self.assertIn("_auth_user_id", self.client.session)


@override_settings(SITE_URL="https://example.test", EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class RegisterTests(TestCase):
    def setUp(self):
        cache.clear()
        CustomUser.objects.create_user("known@example.com")

    def register(self, email):
        return self.client.post(
            reverse("register"),
            {"email": email, "first_name": "A", "last_name": "B", "password": ""},
            follow=True,
        )

    def test_existing_email_gets_the_same_response_as_a_new_one(self):
        known = self.register("known@example.com")
        new = self.register("new@example.com")
        self.assertEqual(
            [str(m) for m in known.context["messages"]],
            [str(m) for m in new.context["messages"]],
        )
        self.assertEqual(CustomUser.objects.filter(email__iexact="known@example.com").count(), 1)

    def test_login_is_recorded(self):
        from core.models import UserEvent

        self.client.force_login(CustomUser.objects.get())
        self.assertEqual(UserEvent.objects.filter(event_type="login").count(), 1)
