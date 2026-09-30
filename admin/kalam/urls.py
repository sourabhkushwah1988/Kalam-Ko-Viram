from django.urls import path
from . import views

urlpatterns = [
    path("", views.landing, name="landing"),
    path("about/", views.about, name="about"),
    path("collection/", views.collection, name="collection"),
    path("contact/", views.contact, name="contact"),
    path("writing/", views.writing, name="writing"),
    path("login/", views.login, name="login"),
    path("shayari/", views.shayari, name="shayari"),
]

