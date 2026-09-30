from django.shortcuts import render

def landing(request):
    return render(request, "landing.html")

def login(request):
    return render(request, "login.html")

def about(request):
    return render(request, "about.html")

def collection(request):
    return render(request, "collections.html")

def contact(request):
    return render(request, "contact.html")

def writing(request):
    return render(request, "writing.html")

def base(request):
    return render(request, "base.html")

def shayari(request):
    return render(request, "shayari.html")