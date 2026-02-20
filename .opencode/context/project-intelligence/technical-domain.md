<!-- Context: project-intelligence/technical | Priority: critical | Version: 1.1 | Updated: 2026-02-18 -->

# Technical Domain

**Purpose**: Tech stack, architecture, and development patterns for MicroVolunteer platform.
**Last Updated**: 2026-02-18

## Quick Reference
**Update Triggers**: Tech stack changes | New patterns | Architecture decisions
**Audience**: Developers, AI agents

## Primary Stack
| Layer | Technology | Version | Rationale |
|-------|-----------|---------|-----------|
| Language | Python | 3.12 | Modern Python with performance improvements |
| Framework | Django | 5.x | Full-featured web framework (Admin, Auth, ORM) |
| Database | PostgreSQL | 16 | Robust relational DB for complex queries |
| Frontend | Django Templates | — | Server-side rendering, tight Django integration |
| CSS | Bootstrap | 5 | Responsive design, rapid prototyping |
| Icons | Bootstrap Icons | 1.11 | Icon font for UI elements |
| Maps | Leaflet.js | — | Interactive maps with OpenStreetMap (free, no API key) |
| Charts | Chart.js | — | Dashboard statistics visualization |
| JS | Vanilla JS + Fetch API | — | AJAX for map data, notifications |
| WSGI | Gunicorn | — | Production WSGI server |
| Proxy | Nginx | — | Reverse proxy + static file serving |
| Containers | Docker + docker-compose | — | Containerized deployment |

## Key Libraries
| Library | Purpose |
|---------|---------|
| Pillow | Image processing (avatar resize, validation) |
| django-axes | Brute force protection (block after 5 attempts) |
| django-crispy-forms + crispy-bootstrap5 | Bootstrap 5 styled forms |
| python-decouple | Environment config via `.env` |
| pytest + pytest-django | Testing framework |
| factory_boy | Test data factories |
| coverage | Code coverage reporting |

## Project Structure
```
microvolunteer/
├── config/settings/{base,development,production}.py
├── config/urls.py              # Root URL conf (home + app includes)
├── apps/
│   ├── accounts/               # Auth, profiles, registration, login
│   │   ├── models.py forms.py views.py urls.py
│   │   ├── decorators.py signals.py admin.py
│   ├── requests/               # HelpRequest, Response, Category, map
│   ├── reviews/                # Review (ratings 1-5, comments)
│   ├── notifications/          # In-app notifications (bell icon, signals)
│   └── stats/                  # Dashboard, Chart.js graphs
├── templates/
│   ├── base.html               # Bootstrap 5 layout, navbar, footer, messages
│   ├── home.html               # Landing page with stats
│   └── accounts/               # register, login, profile, profile_edit, password_change
├── static/css/style.css        # Custom styles (card hover, alert animation)
└── media/                      # User uploads (avatars, request photos)
```

## Code Patterns

### Views — Django CBV with LoginRequiredMixin
```python
class ProfileEditView(LoginRequiredMixin, UpdateView):
    model = User
    form_class = UserProfileForm
    template_name = 'accounts/profile_edit.html'
    success_url = reverse_lazy('accounts:profile')

    def get_object(self, queryset=None):
        return self.request.user  # Object-level: user edits only own profile
```

### Registration — UserCreationForm + auto-login
```python
class RegisterView(CreateView):
    form_class = RegisterForm  # extends UserCreationForm
    def form_valid(self, form):
        response = super().form_valid(form)
        login(self.request, self.object, backend='django.contrib.auth.backends.ModelBackend')
        messages.success(self.request, f'Вітаємо, {self.object.first_name}!')
        return response
```

### Dual-Form Editing — user fields + role-specific fields
```python
# In ProfileEditView.post():
form = self.get_form()                    # UserProfileForm
role_form = VolunteerProfileForm(         # or RecipientProfileForm
    request.POST, instance=user.volunteer_profile, prefix='role')
if form.is_valid() and role_form.is_valid():
    form.save(); role_form.save()
```

### Auth Views — customize Django built-ins
```python
class CustomLoginView(LoginView):
    template_name = 'accounts/login.html'
    authentication_form = LoginForm
    redirect_authenticated_user = True  # Prevent re-auth
```

### JSON Endpoint (Map/Charts)
```python
def map_data(request):
    requests = HelpRequest.objects.filter(status="active").values(
        "id", "title", "latitude", "longitude", "urgency")
    return JsonResponse(list(requests), safe=False)
```

### Permissions — Custom Decorators
```python
@login_required
@volunteer_required
def respond_to_request(request, pk):
    help_request = get_object_or_404(HelpRequest, pk=pk, status="active")
```

### Signals — Auto Side Effects
```python
@receiver(post_save, sender=User)
def create_profile(sender, instance, created, **kwargs):
    if created:
        if instance.user_type == "volunteer":
            VolunteerProfile.objects.create(user=instance)
        elif instance.user_type == "recipient":
            RecipientProfile.objects.create(user=instance)
```

### Forms — ModelForm + Crispy + Validation
```python
class RegisterForm(UserCreationForm):
    user_type = forms.ChoiceField(choices=User.UserType.choices, widget=forms.RadioSelect)
    class Meta:
        model = User
        fields = ['username', 'email', 'first_name', 'last_name', 'user_type', 'password1', 'password2']
    def clean_email(self):  # Uniqueness validation
        if User.objects.filter(email=self.cleaned_data['email']).exists():
            raise forms.ValidationError('Email вже існує.')
```

## Naming Conventions
| Type | Convention | Example |
|------|-----------|---------|
| Files/modules | snake_case | `context_processors.py`, `profile_edit.html` |
| Classes/Models | PascalCase | `HelpRequest`, `VolunteerProfile` |
| Functions/views | snake_case | `mark_read`, `expire_requests` |
| URL names | kebab-case | `profile-edit`, `password-change` |
| URL paths | kebab-case | `/accounts/profile/edit/`, `/password-change/` |
| Apps | lowercase | `accounts`, `requests`, `reviews` |
| Templates | snake_case in app dirs | `templates/accounts/profile_edit.html` |
| URL namespaces | app_name in urls.py | `accounts:profile`, `accounts:login` |

## Code Standards
- Django CBV preferred (CreateView, ListView, DetailView, UpdateView)
- `LoginRequiredMixin` on all protected views (first in MRO)
- `redirect_authenticated_user = True` on login/register views
- `django.contrib.messages` for user feedback (success, error, info)
- Dual-form pattern for role-specific profile editing (user form + role form with prefix)
- Django ORM aggregations: `annotate()`, `aggregate()`, `Count`, `Avg`, `Sum`
- Split settings: `base.py` → `development.py` / `production.py`
- App-based modular architecture under `apps/` with `app_name` in urls.py
- Signals for side effects (profile creation, notifications)
- Management commands for scheduled tasks (`expire_requests`)
- Context processors for global template data (`unread_count`)
- Templates extend `base.html`, use `{% block content %}`, `{% load crispy_forms_tags %}`
- Testing: `pytest` + `pytest-django` + `factory_boy`

## Security Requirements
- CSRF tokens on all forms (`{% csrf_token %}`, Django middleware)
- Django ORM only — no raw SQL (parameterized queries)
- Django Templates auto-escaping (XSS protection)
- `django-axes`: block after 5 failed login attempts
- Password validators: `MinimumLengthValidator`, `CommonPasswordValidator`
- Image validation: file type + size ≤ 2MB (`clean_avatar()` in form)
- Object-level permissions: `get_object() → request.user` (user edits only own data)
- Secrets via `python-decouple` + `.env` (SECRET_KEY never in code)
- Coordinate offset ~100m for privacy (exact address after confirmation only)
- Max 10 active requests per user (spam protection)
- `unique_together` constraints (prevent duplicate responses/reviews)
- Email uniqueness validation in `RegisterForm.clean_email()`
- Redirect authenticated users from login/register (`dispatch` override or `redirect_authenticated_user`)
- `enctype="multipart/form-data"` on forms with file uploads

## Codebase References
**Config**: `config/settings/base.py`, `config/urls.py`, `.env.example`
**Accounts** (complete): `apps/accounts/{models,forms,views,urls,decorators,signals,admin}.py`
**Requests** (models only): `apps/requests/{models,utils,admin}.py`
**Reviews** (models only): `apps/reviews/{models,admin}.py`
**Notifications** (models only): `apps/notifications/{models,admin}.py`
**Templates**: `templates/base.html`, `templates/home.html`, `templates/accounts/{register,login,profile,profile_edit,password_change}.html`
**Static**: `static/css/style.css`
**Deployment**: `Dockerfile`, `docker-compose.yml`, `nginx/nginx.conf`

## Related Files
- MicroVolunteer_Plan.md — Full project specification
