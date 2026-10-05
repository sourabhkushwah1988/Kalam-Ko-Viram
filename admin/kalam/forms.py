import re

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm
from django.core.exceptions import ValidationError
from django.utils.text import slugify

from .models import Author, Category, Poetry

User = get_user_model()


def normalize_mobile_number(value):
    digits = re.sub(r"\D", "", str(value or "").strip())
    return digits


class MobileOtpLoginForm(forms.Form):
    mobile_number = forms.CharField(
        label="Mobile number",
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "Enter your mobile number",
            "autocomplete": "tel",
        }),
    )
    otp = forms.CharField(
        label="OTP",
        required=False,
        min_length=6,
        max_length=6,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "Enter 6-digit OTP",
            "autocomplete": "one-time-code",
        }),
    )

    def clean_mobile_number(self):
        mobile = normalize_mobile_number(self.cleaned_data["mobile_number"])
        if len(mobile) < 10 or len(mobile) > 15:
            raise ValidationError("Enter a valid mobile number.")
        return mobile

    def clean_otp(self):
        otp = self.cleaned_data["otp"].strip()
        if otp and not otp.isdigit():
            raise ValidationError("Enter a valid 6-digit OTP.")
        return otp


class ProfileCompletionForm(forms.Form):
    name = forms.CharField(max_length=100, label="Name", widget=forms.TextInput(attrs={
        "class": "form-control",
        "placeholder": "Enter your full name",
        "autocomplete": "name",
    }))
    username = forms.CharField(max_length=150, label="Username", widget=forms.TextInput(attrs={
        "class": "form-control",
        "placeholder": "Choose a username",
        "autocomplete": "username",
    }))
    email = forms.EmailField(label="Email", widget=forms.EmailInput(attrs={
        "class": "form-control",
        "placeholder": "Enter your email",
        "autocomplete": "email",
    }))
    city = forms.CharField(max_length=100, label="City", widget=forms.TextInput(attrs={
        "class": "form-control",
        "placeholder": "Enter your city",
        "autocomplete": "address-level2",
    }))

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("This username is already taken.")
        return username

    def clean_email(self):
        email = self.cleaned_data["email"].strip()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("This email is already in use.")
        return email


class VisitorSignupForm(UserCreationForm):
    email = forms.EmailField(widget=forms.EmailInput(attrs={
        "class": "form-control",
        "placeholder": "Email address",
        "autocomplete": "email",
    }))

    class Meta:
        model = User
        fields = ("first_name", "last_name", "username", "email")
        widgets = {
            "first_name": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "First name",
                "autocomplete": "given-name",
            }),
            "last_name": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Last name",
                "autocomplete": "family-name",
            }),
            "username": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Choose a username",
                "autocomplete": "username",
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.pop("autofocus", None)
        self.fields["password1"].widget.attrs.update({
            "class": "form-control",
            "placeholder": "Create a password",
            "autocomplete": "new-password",
        })
        self.fields["password2"].widget.attrs.update({
            "class": "form-control",
            "placeholder": "Confirm password",
            "autocomplete": "new-password",
        })

    def clean_email(self):
        email = self.cleaned_data["email"].strip()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email


class PoetryForm(forms.ModelForm):
    class Meta:
        model = Poetry
        fields = (
            "title",
            "author",
            "category",
            "poetry_type",
            "language",
            "content",
            "is_featured",
            "is_trending",
            "is_daily",
            "status",
        )
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "author": forms.Select(attrs={"class": "form-control"}),
            "category": forms.Select(attrs={"class": "form-control"}),
            "poetry_type": forms.Select(attrs={"class": "form-control"}),
            "language": forms.TextInput(attrs={"class": "form-control"}),
            "content": forms.Textarea(attrs={"class": "form-control", "rows": 8}),
            "status": forms.Select(attrs={"class": "form-control"}),
        }


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ("name", "slug")
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "slug": forms.TextInput(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["slug"].required = False

    def clean_slug(self):
        slug = slugify(self.cleaned_data.get("slug") or self.cleaned_data.get("name", ""))
        queryset = Category.objects.filter(slug=slug)
        if self.instance.pk:
            queryset = queryset.exclude(pk=self.instance.pk)
        if not slug or queryset.exists():
            raise ValidationError("Enter a unique category slug.")
        return slug


class AuthorForm(forms.ModelForm):
    class Meta:
        model = Author
        fields = ("name", "slug", "bio")
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "slug": forms.TextInput(attrs={"class": "form-control"}),
            "bio": forms.Textarea(attrs={"class": "form-control", "rows": 5}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["slug"].required = False

    def clean_slug(self):
        slug = slugify(self.cleaned_data.get("slug") or self.cleaned_data.get("name", ""))
        queryset = Author.objects.filter(slug=slug)
        if self.instance.pk:
            queryset = queryset.exclude(pk=self.instance.pk)
        if not slug or queryset.exists():
            raise ValidationError("Enter a unique author slug.")
        return slug