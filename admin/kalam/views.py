import logging
import secrets
from functools import wraps
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import DatabaseError, connection
from django.db.models import Count, Q
from django.db.models.deletion import ProtectedError
from django.contrib.auth import get_user_model, login as auth_login, logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods, require_POST

from .forms import (
    AuthorForm,
    CategoryForm,
    MobileOtpLoginForm,
    PoetryForm,
    ProfileCompletionForm,
)
from .models import Author, Category, OtpVerification, Poetry, UserProfile

logger = logging.getLogger(__name__)


def _published_poetry():
    return Poetry.objects.filter(status=Poetry.Status.PUBLISHED).select_related("author", "category")


def _published_categories():
    return Category.objects.annotate(
        published_count=Count("poetry", filter=Q(poetry__status=Poetry.Status.PUBLISHED))
    ).filter(published_count__gt=0).order_by("name")


def _poetry_data(poetry_items):
    return [
        {
            "id": str(poetry.pk),
            "title": poetry.title,
            "text": poetry.content,
            "author": poetry.author.name,
            "cat": poetry.category.name,
            "cat_slug": poetry.category.slug,
            "type": poetry.poetry_type,
            "date": (poetry.publish_date or poetry.created_at).date().isoformat(),
            "likes": 0,
        }
        for poetry in poetry_items
    ]


def _post_auth_redirect(request):
    next_url = request.POST.get("next") or request.GET.get("next")
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(next_url)
    return redirect("landing")


def login(request):
    if request.user.is_authenticated:
        return redirect("landing")

    next_url = request.POST.get("next") or request.GET.get("next", "")
    login_form = MobileOtpLoginForm(request.POST or None)
    profile_form = ProfileCompletionForm(request.POST or None)

    if request.method == "POST":
        form_type = request.POST.get("form_type")
        mobile_number = (request.POST.get("mobile_number") or "").strip()
        otp_value = (request.POST.get("otp") or "").strip()

        if form_type == "profile_complete":
            if profile_form.is_valid():
                pending_profile = request.session.get("pending_profile") or {}
                mobile_number = pending_profile.get("mobile_number")
                if not mobile_number:
                    return redirect("login")

                name = profile_form.cleaned_data["name"].strip()
                username = profile_form.cleaned_data["username"].strip()
                email = profile_form.cleaned_data["email"].strip()
                city = profile_form.cleaned_data["city"].strip()

                user = get_user_model().objects.create_user(
                    username=username,
                    email=email,
                    password=secrets.token_urlsafe(18),
                    first_name=name,
                )
                UserProfile.objects.create(user=user, mobile_number=mobile_number, city=city)
                auth_login(request, user)
                request.session.pop("pending_otp", None)
                request.session.pop("pending_profile", None)
                return _post_auth_redirect(request)
            return render(request, "login.html", {
                "form": login_form,
                "profile_form": profile_form,
                "show_profile_form": True,
                "mobile_number": request.session.get("pending_profile", {}).get("mobile_number", ""),
                "next": next_url,
            })

        if request.POST.get("action") == "send_otp" or (
            "action" not in request.POST and not otp_value and not request.session.get("pending_otp")
        ):
            if login_form.is_valid():
                mobile_number = login_form.cleaned_data["mobile_number"]
                OtpVerification.objects.filter(mobile_number=mobile_number, is_used=False).update(is_used=True)
                otp_code = str(secrets.randbelow(900000) + 100000)
                otp_record = OtpVerification.objects.create(
                    mobile_number=mobile_number,
                    otp=otp_code,
                    expires_at=timezone.now() + timedelta(minutes=5),
                )
                request.session["pending_otp"] = {
                    "mobile_number": mobile_number,
                    "otp_id": otp_record.id,
                }
                return render(request, "login.html", {
                    "form": MobileOtpLoginForm(initial={"mobile_number": mobile_number}),
                    "mode": "login",
                    "next": next_url,
                    "otp_sent": True,
                    "mobile_number": mobile_number,
                    **({"dev_otp": otp_code} if settings.SHOW_DEV_OTP else {}),
                })
            return render(request, "login.html", {
                "form": login_form,
                "mode": "login",
                "next": next_url,
            })

        if not login_form.is_valid():
            return render(request, "login.html", {
                "form": login_form,
                "mode": "login",
                "next": next_url,
                "otp_sent": bool(request.session.get("pending_otp")),
                "mobile_number": request.session.get("pending_otp", {}).get("mobile_number", ""),
            })

        mobile_number = login_form.cleaned_data["mobile_number"]
        otp_value = login_form.cleaned_data["otp"]
        pending = request.session.get("pending_otp")
        if not pending:
            login_form.add_error("otp", "OTP session expired. Please request a new OTP.")
            return render(request, "login.html", {
                "form": login_form,
                "mode": "login",
                "next": next_url,
            })

        otp_record = OtpVerification.objects.filter(id=pending.get("otp_id")).order_by("-created_at").first()
        if (
            otp_record is None
            or otp_record.mobile_number != pending.get("mobile_number")
            or mobile_number != pending.get("mobile_number")
        ):
            login_form.add_error("otp", "Invalid OTP. Please try again.")
            return render(request, "login.html", {
                "form": login_form,
                "mode": "login",
                "next": next_url,
                "otp_sent": True,
                "mobile_number": pending.get("mobile_number", mobile_number),
            })

        if otp_record.expires_at <= timezone.now() or otp_record.is_used:
            login_form.add_error("otp", "This OTP has expired. Please request a new one.")
            return render(request, "login.html", {
                "form": login_form,
                "mode": "login",
                "next": next_url,
                "otp_sent": True,
                "mobile_number": pending.get("mobile_number", mobile_number),
            })

        if otp_record.otp != otp_value:
            otp_record.attempts += 1
            otp_record.save(update_fields=("attempts",))
            if otp_record.attempts >= 5:
                otp_record.is_used = True
                otp_record.save(update_fields=("attempts", "is_used"))
            login_form.add_error("otp", "Invalid OTP. Please try again.")
            return render(request, "login.html", {
                "form": login_form,
                "mode": "login",
                "next": next_url,
                "otp_sent": True,
                "mobile_number": pending.get("mobile_number", mobile_number),
            })

        otp_record.verified_at = timezone.now()
        otp_record.is_used = True
        otp_record.save(update_fields=("verified_at", "is_used"))

        profile = UserProfile.objects.filter(mobile_number=pending.get("mobile_number")).select_related("user").first()
        if profile:
            auth_login(request, profile.user)
            request.session.pop("pending_otp", None)
            return _post_auth_redirect(request)

        request.session["pending_profile"] = {"mobile_number": pending.get("mobile_number")}
        return render(request, "login.html", {
            "form": MobileOtpLoginForm(initial={"mobile_number": pending.get("mobile_number")}),
            "profile_form": ProfileCompletionForm(),
            "show_profile_form": True,
            "mobile_number": pending.get("mobile_number"),
            "next": next_url,
        })

    return render(request, "login.html", {
        "form": login_form,
        "mode": "login",
        "next": next_url,
    })


@require_POST
def logout(request):
    auth_logout(request)
    return redirect("landing")


def landing(request):
    published = _published_poetry()
    categories = _published_categories()
    search_data = [
        f"{category.name} — {category.published_count} verses"
        for category in categories
    ]
    search_data.extend(published.order_by().values_list("author__name", flat=True).distinct())
    search_data.extend(published.order_by().values_list("title", flat=True))

    return render(request, "landing.html", {
        "trending_poetry": published.filter(
            is_trending=True,
            poetry_type=Poetry.PoetryType.SHAYARI,
        )[:6],
        "hero_poetry_data": _poetry_data(published[:8]),
        "daily_poetry": published.filter(is_daily=True).first(),
        "categories": categories,
        "homepage_search_data": search_data,
        "spotlight_poetry": published.filter(author__name__iexact="Jaun Elia")[:4],
    })

@login_required(login_url="login")
def about(request):
    return render(request, "about.html")

@login_required(login_url="login")
def collection(request):
    return render(request, "collections.html", {
        "poetry_data": _poetry_data(_published_poetry()),
        "categories": _published_categories(),
    })

@login_required(login_url="login")
def contact(request):
    return render(request, "contact.html")

@login_required(login_url="login")
def writing(request):
    return render(request, "writing.html", {
        "poetry_data": _poetry_data(_published_poetry()),
        "categories": _published_categories(),
    })

@login_required(login_url="login")
def base(request):
    return render(request, "base.html")

@login_required(login_url="login")
def shayari(request):
    all_published = _published_poetry()
    poetry = all_published
    query = request.GET.get("q", "").strip()
    category_slug = request.GET.get("category", "").strip()
    if query:
        poetry = poetry.filter(
            Q(title__icontains=query)
            | Q(content__icontains=query)
            | Q(author__name__icontains=query)
            | Q(category__name__icontains=query)
        )
    if category_slug:
        poetry = poetry.filter(category__slug=category_slug)

    return render(request, "shayari.html", {
        "query": query,
        "selected_category": category_slug,
        "categories": _published_categories(),
        "poetry_count": all_published.filter(poetry_type=Poetry.PoetryType.SHAYARI).count(),
        "category_count": _published_categories().count(),
        "featured_poetry": poetry.filter(is_featured=True).first(),
        "trending_poetry": poetry.filter(is_trending=True)[:8],
        "latest_poetry": poetry.order_by("-created_at")[:6],
    })


portal_login = LoginView.as_view(
    template_name="admin_portal/login.html",
    redirect_authenticated_user=True,
    next_page="portal_dashboard",
)


def _portal_permission_required(permission):
    def decorator(view):
        @login_required(login_url="portal_login")
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if not request.user.has_perm(permission):
                raise PermissionDenied
            return view(request, *args, **kwargs)

        return wrapped

    return decorator


def _portal_dashboard_access_required(view):
    @login_required(login_url="portal_login")
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        permissions = (
            "kalam.view_poetry",
            "kalam.view_author",
            "kalam.view_category",
            "auth.view_user",
        )
        if not request.user.is_superuser and not any(
            request.user.has_perm(permission) for permission in permissions
        ):
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return wrapped


def _page(request, queryset):
    return Paginator(queryset, 20).get_page(request.GET.get("page"))


@_portal_dashboard_access_required
def portal_dashboard(request):
    can_view_poetry = request.user.has_perm("kalam.view_poetry")
    recent_poetry = (
        Poetry.objects.select_related("author", "category")[:6]
        if can_view_poetry else Poetry.objects.none()
    )
    return render(request, "admin_portal/dashboard.html", {
        "poetry_count": Poetry.objects.count() if can_view_poetry else None,
        "published_count": Poetry.objects.filter(status=Poetry.Status.PUBLISHED).count()
        if can_view_poetry else None,
        "draft_count": Poetry.objects.filter(status=Poetry.Status.DRAFT).count()
        if can_view_poetry else None,
        "author_count": Author.objects.count() if request.user.has_perm("kalam.view_author") else None,
        "category_count": Category.objects.count()
        if request.user.has_perm("kalam.view_category") else None,
        "user_count": get_user_model().objects.count()
        if request.user.has_perm("auth.view_user") else None,
        "recent_poetry": recent_poetry,
    })


@_portal_permission_required("kalam.view_poetry")
def portal_poetry_list(request):
    queryset = Poetry.objects.select_related("author", "category")
    search = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()
    if search:
        queryset = queryset.filter(
            Q(title__icontains=search)
            | Q(content__icontains=search)
            | Q(author__name__icontains=search)
        )
    if status in Poetry.Status.values:
        queryset = queryset.filter(status=status)
    return render(request, "admin_portal/poetry/list.html", {
        "page_obj": _page(request, queryset),
        "search": search,
        "selected_status": status,
    })


@_portal_permission_required("kalam.add_poetry")
@require_http_methods(["GET", "POST"])
def portal_poetry_create(request):
    form = PoetryForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        poetry = form.save(commit=False)
        if poetry.status == Poetry.Status.PUBLISHED and poetry.publish_date is None:
            poetry.publish_date = timezone.now()
        poetry.save()
        return redirect("portal_poetry_list")
    return render(request, "admin_portal/poetry/form.html", {
        "form": form,
        "page_title": "New poetry",
        "submit_label": "Save poetry",
    })


@_portal_permission_required("kalam.change_poetry")
@require_http_methods(["GET", "POST"])
def portal_poetry_edit(request, pk):
    poetry = get_object_or_404(Poetry, pk=pk)
    form = PoetryForm(request.POST or None, instance=poetry)
    if request.method == "POST" and form.is_valid():
        poetry = form.save(commit=False)
        if poetry.status == Poetry.Status.PUBLISHED and poetry.publish_date is None:
            poetry.publish_date = timezone.now()
        poetry.save()
        return redirect("portal_poetry_list")
    return render(request, "admin_portal/poetry/form.html", {
        "form": form,
        "page_title": "Edit poetry",
        "submit_label": "Save changes",
    })


@_portal_permission_required("kalam.delete_poetry")
@require_http_methods(["GET", "POST"])
def portal_poetry_delete(request, pk):
    poetry = get_object_or_404(Poetry, pk=pk)
    if request.method == "POST":
        poetry.delete()
        return redirect("portal_poetry_list")
    return render(request, "admin_portal/confirm_delete.html", {
        "object": poetry,
        "cancel_url": "portal_poetry_list",
    })


@_portal_permission_required("kalam.view_author")
def portal_author_list(request):
    queryset = Author.objects.annotate(poetry_count=Count("poetry")).order_by("name")
    search = request.GET.get("q", "").strip()
    if search:
        queryset = queryset.filter(Q(name__icontains=search) | Q(bio__icontains=search))
    return render(request, "admin_portal/authors/list.html", {
        "page_obj": _page(request, queryset),
        "search": search,
    })


@_portal_permission_required("kalam.add_author")
@require_http_methods(["GET", "POST"])
def portal_author_create(request):
    form = AuthorForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("portal_author_list")
    return render(request, "admin_portal/entity_form.html", {
        "form": form,
        "page_title": "New author",
        "submit_label": "Save author",
        "cancel_url": "portal_author_list",
    })


@_portal_permission_required("kalam.change_author")
@require_http_methods(["GET", "POST"])
def portal_author_edit(request, pk):
    author = get_object_or_404(Author, pk=pk)
    form = AuthorForm(request.POST or None, instance=author)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("portal_author_list")
    return render(request, "admin_portal/entity_form.html", {
        "form": form,
        "page_title": "Edit author",
        "submit_label": "Save changes",
        "cancel_url": "portal_author_list",
    })


@_portal_permission_required("kalam.delete_author")
@require_http_methods(["GET", "POST"])
def portal_author_delete(request, pk):
    author = get_object_or_404(Author, pk=pk)
    if request.method == "POST":
        try:
            author.delete()
        except ProtectedError:
            return render(request, "admin_portal/confirm_delete.html", {
                "object": author,
                "cancel_url": "portal_author_list",
                "delete_error": "This author is still referenced by poetry. Reassign or delete those entries first.",
            }, status=409)
        return redirect("portal_author_list")
    return render(request, "admin_portal/confirm_delete.html", {
        "object": author,
        "cancel_url": "portal_author_list",
    })


@_portal_permission_required("kalam.view_category")
def portal_category_list(request):
    queryset = Category.objects.annotate(poetry_count=Count("poetry")).order_by("name")
    search = request.GET.get("q", "").strip()
    if search:
        queryset = queryset.filter(name__icontains=search)
    return render(request, "admin_portal/categories/list.html", {
        "page_obj": _page(request, queryset),
        "search": search,
    })


@_portal_permission_required("kalam.add_category")
@require_http_methods(["GET", "POST"])
def portal_category_create(request):
    form = CategoryForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("portal_category_list")
    return render(request, "admin_portal/entity_form.html", {
        "form": form,
        "page_title": "New category",
        "submit_label": "Save category",
        "cancel_url": "portal_category_list",
    })


@_portal_permission_required("kalam.change_category")
@require_http_methods(["GET", "POST"])
def portal_category_edit(request, pk):
    category = get_object_or_404(Category, pk=pk)
    form = CategoryForm(request.POST or None, instance=category)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("portal_category_list")
    return render(request, "admin_portal/entity_form.html", {
        "form": form,
        "page_title": "Edit category",
        "submit_label": "Save changes",
        "cancel_url": "portal_category_list",
    })


@_portal_permission_required("kalam.delete_category")
@require_http_methods(["GET", "POST"])
def portal_category_delete(request, pk):
    category = get_object_or_404(Category, pk=pk)
    if request.method == "POST":
        try:
            category.delete()
        except ProtectedError:
            return render(request, "admin_portal/confirm_delete.html", {
                "object": category,
                "cancel_url": "portal_category_list",
                "delete_error": "This category is still referenced by poetry. Reassign or delete those entries first.",
            }, status=409)
        return redirect("portal_category_list")
    return render(request, "admin_portal/confirm_delete.html", {
        "object": category,
        "cancel_url": "portal_category_list",
    })


@_portal_permission_required("auth.view_user")
def portal_user_list(request):
    queryset = get_user_model().objects.order_by("-date_joined")
    search = request.GET.get("q", "").strip()
    if search:
        queryset = queryset.filter(
            Q(username__icontains=search)
            | Q(email__icontains=search)
            | Q(first_name__icontains=search)
            | Q(last_name__icontains=search)
        )
    return render(request, "admin_portal/users/list.html", {
        "page_obj": _page(request, queryset),
        "search": search,
    })


@_portal_permission_required("kalam.view_poetry")
def portal_analytics(request):
    can_view_author = request.user.has_perm("kalam.view_author")
    can_view_category = request.user.has_perm("kalam.view_category")
    can_view_user = request.user.has_perm("auth.view_user")
    return render(request, "admin_portal/analytics.html", {
        "poetry_count": Poetry.objects.count(),
        "published_count": Poetry.objects.filter(status=Poetry.Status.PUBLISHED).count(),
        "draft_count": Poetry.objects.filter(status=Poetry.Status.DRAFT).count(),
        "author_count": Author.objects.count() if can_view_author else None,
        "category_count": Category.objects.count() if can_view_category else None,
        "user_count": get_user_model().objects.count() if can_view_user else None,
        "poetry_by_type": Poetry.objects.values("poetry_type").annotate(total=Count("id")).order_by(
            "poetry_type"
        ),
        "poetry_by_category": (
            Category.objects.annotate(poetry_count=Count("poetry")).order_by("-poetry_count", "name")
            if can_view_category else Category.objects.none()
        ),
    })


@_portal_dashboard_access_required
def portal_settings(request):
    database = settings.DATABASES["default"]
    return render(request, "admin_portal/settings.html", {
        "database_engine": database["ENGINE"].rsplit(".", 1)[-1],
        "debug_enabled": settings.DEBUG,
        "timezone_name": settings.TIME_ZONE,
    })


@_portal_dashboard_access_required
def portal_documentation(request):
    return render(request, "admin_portal/documentation.html")


@_portal_dashboard_access_required
def portal_system_health(request):
    try:
        connection.ensure_connection()
        database_status = "Connected"
        database_error = ""
    except DatabaseError:
        logger.exception("Admin portal could not connect to the database")
        database_status = "Unavailable"
        database_error = "The database connection failed. Check the server logs for details."
    return render(request, "admin_portal/system_health.html", {
        "database_status": database_status,
        "database_error": database_error,
        "debug_enabled": settings.DEBUG,
        "poetry_count": (
            Poetry.objects.count()
            if database_status == "Connected" and request.user.has_perm("kalam.view_poetry")
            else None
        ),
    })


@login_required(login_url="portal_login")
@require_POST
def portal_logout(request):
    auth_logout(request)
    return redirect("portal_login")