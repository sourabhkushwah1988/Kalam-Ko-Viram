from django.contrib.auth import get_user_model
from django.core.validators import RegexValidator
from django.db import models


User = get_user_model()


class UserProfile(models.Model):
	user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
	mobile_number = models.CharField(
		max_length=15,
		unique=True,
		db_index=True,
		validators=[RegexValidator(regex=r"^\+?[1-9]\d{9,14}$", message="Enter a valid mobile number.")],
	)
	city = models.CharField(max_length=100, blank=True, default="")
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		verbose_name = "user profile"
		verbose_name_plural = "user profiles"

	def __str__(self):
		return f"{self.user.username} ({self.mobile_number})"


class OtpVerification(models.Model):
	mobile_number = models.CharField(max_length=15)
	otp = models.CharField(max_length=6)
	expires_at = models.DateTimeField()
	verified_at = models.DateTimeField(null=True, blank=True)
	attempts = models.PositiveSmallIntegerField(default=0)
	is_used = models.BooleanField(default=False)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ("-created_at",)

	def __str__(self):
		return f"OTP for {self.mobile_number}"


class Category(models.Model):
	name = models.CharField(max_length=100)
	slug = models.SlugField(max_length=120, unique=True)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ("name",)
		verbose_name_plural = "categories"

	def __str__(self):
		return self.name


class Author(models.Model):
	name = models.CharField(max_length=150)
	slug = models.SlugField(max_length=170, unique=True)
	bio = models.TextField(blank=True)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ("name",)

	def __str__(self):
		return self.name


class Poetry(models.Model):
	class PoetryType(models.TextChoices):
		SHAYARI = "shayari", "Shayari"
		KAVITA = "kavita", "Kavita"
		GHAZAL = "ghazal", "Ghazal"
		NAZM = "nazm", "Nazm"

	class Status(models.TextChoices):
		DRAFT = "draft", "Draft"
		PUBLISHED = "published", "Published"

	title = models.CharField(max_length=200)
	content = models.TextField()
	author = models.ForeignKey(Author, on_delete=models.PROTECT, related_name="poetry")
	category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="poetry")
	poetry_type = models.CharField(max_length=20, choices=PoetryType.choices, default=PoetryType.SHAYARI)
	language = models.CharField(max_length=30, default="Hindi")
	status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT)
	publish_date = models.DateTimeField(blank=True, null=True)
	is_featured = models.BooleanField(default=False)
	is_trending = models.BooleanField(default=False)
	is_daily = models.BooleanField(default=False)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ("-created_at",)
		verbose_name_plural = "poetry"

	def __str__(self):
		return self.title
