# TODO

- [x] Inspect existing Django templates (`base.html`, `landing.html`, `writing.html`, `about.html`, `contact.html`).
- [x] Update `admin/templates/about.html` to use `{% extends 'base.html' %}` and render inside `{% block content %}` (navbar + footer already in `base.html`).
- [x] Fix Django routing bug in `admin/kalam/urls.py` (missing view function imports caused `NameError`).
- [x] Run `python admin/manage.py check` to ensure no Django errors remain.

