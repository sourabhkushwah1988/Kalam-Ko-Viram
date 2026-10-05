from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from .models import Author, Category, OtpVerification, Poetry, UserProfile


class PublishedPoetryVisibilityTests(TestCase):
	@classmethod
	def setUpTestData(cls):
		cls.author = Author.objects.create(name="Test Poet", slug="test-poet")
		cls.category = Category.objects.create(name="Test Category", slug="test-category")
		cls.published = Poetry.objects.create(
			title="Published Test Poem",
			content="PUBLIC_VISIBLE_SAMPLE_927",
			author=cls.author,
			category=cls.category,
			status=Poetry.Status.PUBLISHED,
		)
		Poetry.objects.create(
			title="Draft Test Poem",
			content="PRIVATE_DRAFT_SAMPLE_428",
			author=cls.author,
			category=cls.category,
			status=Poetry.Status.DRAFT,
		)

	def setUp(self):
		self.reader = get_user_model().objects.create_user(
			username="reader-test",
			email="reader@example.com",
			password="ReaderSecure#9284River",
		)
		self.client.force_login(self.reader)

	def test_landing_page_is_public_but_content_pages_require_login(self):
		anonymous_client = Client()
		response = anonymous_client.get("/")
		self.assertEqual(response.status_code, 200)

		for path in ("/about/", "/collection/", "/contact/", "/writing/", "/shayari/"):
			with self.subTest(path=path):
				response = anonymous_client.get(path)
				self.assertEqual(response.status_code, 302)
				self.assertEqual(response.url, f"/login/?next={path}")

	def test_drafts_never_appear_on_public_pages(self):
		for path in ("/", "/writing/", "/collection/", "/shayari/"):
			with self.subTest(path=path):
				response = self.client.get(path)
				self.assertEqual(response.status_code, 200)
				self.assertContains(response, "PUBLIC_VISIBLE_SAMPLE_927")
				self.assertNotContains(response, "PRIVATE_DRAFT_SAMPLE_428")

	def test_shayari_search_uses_published_database_records(self):
		response = self.client.get("/shayari/", {"q": "PUBLIC_VISIBLE_SAMPLE"})

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "PUBLIC_VISIBLE_SAMPLE_927")
		self.assertNotContains(response, "PRIVATE_DRAFT_SAMPLE_428")

	def test_admin_route_remains_available(self):
		staff_user = get_user_model().objects.create_superuser(
			username="admin-test", email="admin@example.com", password="test-password"
		)
		self.client.force_login(staff_user)

		for path in (
			"/admin/",
			"/admin/auth/user/",
			"/admin/kalam/category/",
			"/admin/kalam/author/",
			"/admin/kalam/poetry/",
			"/admin/kalam/poetry/add/",
		):
			with self.subTest(path=path):
				self.assertEqual(self.client.get(path).status_code, 200)
		self.assertContains(self.client.get("/admin/auth/user/"), "reader-test")

	def test_signup_route_is_removed(self):
		self.client.logout()
		response = self.client.get("/register/")
		self.assertEqual(response.status_code, 404)

	def test_login_accepts_mobile_otp_and_logout_clears_session(self):
		self.client.logout()
		UserProfile.objects.create(user=self.reader, mobile_number="9876543210", city="Delhi")

		response = self.client.post("/login/", {
			"action": "send_otp",
			"mobile_number": "9876543210",
		})
		self.assertEqual(response.status_code, 200)
		self.assertRegex(response.context["dev_otp"], r"^\d{6}$")
		self.assertContains(response, f"DEVELOPMENT OTP: <strong>{response.context['dev_otp']}</strong>")
		otp_record = OtpVerification.objects.filter(mobile_number="9876543210").order_by("-created_at").first()
		self.assertIsNotNone(otp_record)
		self.assertGreater(otp_record.expires_at, timezone.now())
		self.assertLessEqual(otp_record.expires_at, timezone.now() + timedelta(minutes=5))

		self.client.post("/login/", {
			"action": "send_otp",
			"mobile_number": "9876543210",
		})
		otp_record.refresh_from_db()
		self.assertTrue(otp_record.is_used)
		otp_record = OtpVerification.objects.filter(mobile_number="9876543210").order_by("-created_at").first()

		response = self.client.post("/login/", {
			"action": "verify_otp",
			"mobile_number": "9876543210",
			"otp": otp_record.otp,
		})
		self.assertRedirects(response, "/")
		self.assertTrue(self.client.get("/").wsgi_request.user.is_authenticated)
		self.reader.refresh_from_db()
		self.assertIsNotNone(self.reader.last_login)
		self.assertEqual(self.client.post("/logout/").status_code, 302)
		self.assertEqual(self.client.get("/").status_code, 200)

	def test_new_user_creates_profile_and_logs_in_via_mobile_otp(self):
		self.client.logout()
		response = self.client.post("/login/", {
			"action": "send_otp",
			"mobile_number": "9999988888",
		})
		self.assertEqual(response.status_code, 200)
		otp_record = OtpVerification.objects.filter(mobile_number="9999988888").order_by("-created_at").first()
		self.assertIsNotNone(otp_record)

		response = self.client.post("/login/", {
			"action": "verify_otp",
			"mobile_number": "9999988888",
			"otp": otp_record.otp,
		})
		self.assertEqual(response.status_code, 200)
		self.assertTrue(response.context["show_profile_form"])

		response = self.client.post("/login/", {
			"form_type": "profile_complete",
			"name": "Mira Reader",
			"username": "mira-reader",
			"email": "mira@example.com",
			"city": "Delhi",
		})
		self.assertRedirects(response, "/")
		self.assertTrue(self.client.get("/").wsgi_request.user.is_authenticated)
		user = get_user_model().objects.get(username="mira-reader")
		self.assertEqual(user.first_name, "Mira Reader")
		self.assertEqual(user.email, "mira@example.com")
		self.assertEqual(user.profile.mobile_number, "9999988888")
		self.assertEqual(user.profile.city, "Delhi")

	@override_settings(SHOW_DEV_OTP=False)
	def test_dev_otp_is_not_displayed_when_setting_is_disabled(self):
		self.client.logout()
		response = self.client.post("/login/", {
			"action": "send_otp",
			"mobile_number": "9876543210",
		})
		self.assertEqual(response.status_code, 200)
		self.assertNotIn("dev_otp", response.context)
		self.assertNotContains(response, "DEVELOPMENT OTP:")

	def test_invalid_and_expired_otps_are_rejected(self):
		self.client.logout()
		self.client.post("/login/", {
			"action": "send_otp",
			"mobile_number": "9876543210",
		})
		otp_record = OtpVerification.objects.get(mobile_number="9876543210")

		response = self.client.post("/login/", {
			"action": "verify_otp",
			"mobile_number": "9876543210",
			"otp": "abcdef",
		})
		self.assertContains(response, "Enter a valid 6-digit OTP.")
		self.assertFalse(response.wsgi_request.user.is_authenticated)

		response = self.client.post("/login/", {
			"action": "verify_otp",
			"mobile_number": "9876543210",
			"otp": "000000",
		})
		self.assertContains(response, "Invalid OTP. Please try again.")
		otp_record.refresh_from_db()
		otp_record.expires_at = timezone.now() - timedelta(seconds=1)
		otp_record.save(update_fields=("expires_at",))

		response = self.client.post("/login/", {
			"action": "verify_otp",
			"mobile_number": "9876543210",
			"otp": otp_record.otp,
		})
		self.assertContains(response, "This OTP has expired. Please request a new one.")
		self.assertFalse(response.wsgi_request.user.is_authenticated)

	def test_initial_migration_imports_existing_sample_poetry(self):
		self.assertTrue(
			Poetry.objects.filter(
				title="Khaamoshi ki Rasm",
				status=Poetry.Status.PUBLISHED,
			).exists()
		)


class AdminPortalTests(TestCase):
	@classmethod
	def setUpTestData(cls):
		cls.author = Author.objects.create(name="Portal Poet", slug="portal-poet")
		cls.category = Category.objects.create(name="Portal Category", slug="portal-category")
		cls.user = get_user_model().objects.create_user(
			username="portal-editor",
			email="editor@example.com",
			password="secure-test-password",
		)
		from django.contrib.auth.models import Permission

		permissions = Permission.objects.filter(
			content_type__app_label__in=("kalam", "auth"),
			codename__in=(
				"view_poetry",
				"add_poetry",
				"change_poetry",
				"delete_poetry",
				"view_author",
				"add_author",
				"change_author",
				"delete_author",
				"view_category",
				"add_category",
				"change_category",
				"delete_category",
				"view_user",
			),
		)
		cls.user.user_permissions.add(*permissions)

	def test_portal_requires_login_and_model_permissions(self):
		self.assertRedirects(
			self.client.get("/portal/"),
			"/portal/login/?next=/portal/",
		)
		unauthorized = get_user_model().objects.create_user(
			username="no-portal-access",
			password="secure-test-password",
		)
		self.client.force_login(unauthorized)
		self.assertEqual(self.client.get("/portal/").status_code, 403)
		self.assertEqual(self.client.get("/portal/poetry/").status_code, 403)

	def test_read_only_user_permission_does_not_expose_poetry_dashboard_data(self):
		from django.contrib.auth.models import Permission

		reader = get_user_model().objects.create_user(
			username="portal-user-reader",
			password="secure-test-password",
		)
		reader.user_permissions.add(
			Permission.objects.get(content_type__app_label="auth", codename="view_user")
		)
		Poetry.objects.create(
			title="Hidden from user-only portal role",
			content="Private poetry content",
			author=self.author,
			category=self.category,
		)
		self.client.force_login(reader)

		response = self.client.get("/portal/")

		self.assertEqual(response.status_code, 200)
		self.assertNotContains(response, "Hidden from user-only portal role")
		self.assertNotContains(response, "Total poetry")

	def test_password_portal_login_and_support_pages_render(self):
		response = self.client.post("/portal/login/", {
			"username": "portal-editor",
			"password": "secure-test-password",
		})

		self.assertRedirects(response, "/portal/")
		for path in (
			"/portal/poetry/new/",
			"/portal/users/",
			"/portal/settings/",
			"/portal/documentation/",
			"/portal/system-health/",
		):
			with self.subTest(path=path):
				page = self.client.get(path)
				self.assertEqual(page.status_code, 200)
				if path == "/portal/poetry/new/":
					self.assertContains(page, "Save as Draft")
					self.assertContains(page, "Save & Publish Live")

	def test_dashboard_uses_database_counts_and_reusable_portal_shell(self):
		Poetry.objects.create(
			title="Portal published count",
			content="A published entry",
			author=self.author,
			category=self.category,
			status=Poetry.Status.PUBLISHED,
		)
		Poetry.objects.create(
			title="Portal draft count",
			content="A private draft",
			author=self.author,
			category=self.category,
		)
		self.client.force_login(self.user)

		response = self.client.get("/portal/")

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.context["poetry_count"], Poetry.objects.count())
		self.assertEqual(
			response.context["published_count"],
			Poetry.objects.filter(status=Poetry.Status.PUBLISHED).count(),
		)
		self.assertEqual(
			response.context["draft_count"],
			Poetry.objects.filter(status=Poetry.Status.DRAFT).count(),
		)
		self.assertContains(response, "Portal draft count")
		self.assertContains(response, "Customer admin portal")

	def test_publishing_from_portal_uses_existing_public_poetry_flow(self):
		self.client.force_login(self.user)
		response = self.client.post("/portal/poetry/new/", {
			"title": "Portal live shayari",
			"author": self.author.pk,
			"category": self.category.pk,
			"poetry_type": Poetry.PoetryType.SHAYARI,
			"language": "Hindi",
			"content": "PORTAL_PUBLISHED_CONTENT_128",
			"is_featured": "on",
			"status": Poetry.Status.PUBLISHED,
		})

		self.assertRedirects(response, "/portal/poetry/")
		poetry = Poetry.objects.get(title="Portal live shayari")
		self.assertIsNotNone(poetry.publish_date)
		self.assertTrue(poetry.is_featured)
		public_response = self.client.get("/shayari/")
		self.assertEqual(public_response.status_code, 200)
		self.assertContains(public_response, "PORTAL_PUBLISHED_CONTENT_128")

	def test_draft_created_in_portal_stays_hidden_from_public_site(self):
		self.client.force_login(self.user)
		self.client.post("/portal/poetry/new/", {
			"title": "Portal private draft",
			"author": self.author.pk,
			"category": self.category.pk,
			"poetry_type": Poetry.PoetryType.SHAYARI,
			"language": "Hindi",
			"content": "PORTAL_PRIVATE_CONTENT_512",
			"status": Poetry.Status.DRAFT,
		})

		response = self.client.get("/shayari/")

		self.assertEqual(response.status_code, 200)
		self.assertNotContains(response, "PORTAL_PRIVATE_CONTENT_512")
		self.assertIsNone(Poetry.objects.get(title="Portal private draft").publish_date)

	def test_author_and_category_crud_are_available_with_matching_permissions(self):
		self.client.force_login(self.user)
		author_response = self.client.post("/portal/authors/new/", {
			"name": "New Portal Author",
			"slug": "new-portal-author",
			"bio": "A short biography",
		})
		category_response = self.client.post("/portal/categories/new/", {
			"name": "New Portal Category",
			"slug": "new-portal-category",
		})

		self.assertRedirects(author_response, "/portal/authors/")
		self.assertRedirects(category_response, "/portal/categories/")
		self.assertTrue(Author.objects.filter(slug="new-portal-author").exists())
		self.assertTrue(Category.objects.filter(slug="new-portal-category").exists())

	def test_analytics_counts_are_dynamic(self):
		self.client.force_login(self.user)
		response = self.client.get("/portal/analytics/")

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.context["poetry_count"], Poetry.objects.count())
		self.assertEqual(response.context["author_count"], Author.objects.count())
		self.assertEqual(response.context["category_count"], Category.objects.count())
