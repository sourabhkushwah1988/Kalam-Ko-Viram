from django.contrib import admin
from django.utils import timezone

from .models import Author, Category, Poetry


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
	list_display = ("name", "slug", "created_at")
	search_fields = ("name", "slug")
	prepopulated_fields = {"slug": ("name",)}


@admin.register(Author)
class AuthorAdmin(admin.ModelAdmin):
	list_display = ("name", "slug", "created_at")
	search_fields = ("name", "bio")
	prepopulated_fields = {"slug": ("name",)}


@admin.register(Poetry)
class PoetryAdmin(admin.ModelAdmin):
	list_display = (
		"title",
		"author",
		"category",
		"status",
		"poetry_type",
		"publish_date",
		"is_featured",
		"is_trending",
		"is_daily",
	)
	list_editable = ("poetry_type", "is_featured", "is_trending", "is_daily")
	list_filter = ("status", "category", "poetry_type", "is_featured", "is_trending", "is_daily")
	search_fields = ("title", "content", "author__name")
	autocomplete_fields = ("author", "category")
	date_hierarchy = "publish_date"
	ordering = ("-publish_date", "-created_at")
	list_per_page = 30
	actions = ("publish_selected", "unpublish_selected")

	@admin.action(description="Publish selected poetry")
	def publish_selected(self, request, queryset):
		for poetry in queryset:
			poetry.status = Poetry.Status.PUBLISHED
			if poetry.publish_date is None:
				poetry.publish_date = timezone.now()
			poetry.save(update_fields=("status", "publish_date", "updated_at"))

	def save_model(self, request, obj, form, change):
		if obj.status == Poetry.Status.PUBLISHED and obj.publish_date is None:
			obj.publish_date = timezone.now()
		super().save_model(request, obj, form, change)

	@admin.action(description="Move selected poetry to drafts")
	def unpublish_selected(self, request, queryset):
		queryset.update(status=Poetry.Status.DRAFT, updated_at=timezone.now())
