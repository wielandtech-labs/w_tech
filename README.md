# WielandTech Portfolio & Blog

A modern Django-based personal portfolio and blog platform.

## 🌟 Features

- Dynamic portfolio showcase
- Blog with rich text editing and tags
- User authentication & profiles
- Activity feed and social features  
- Responsive design
- SEO optimized

## 🛠️ Tech Stack

- **Backend**: Django 5.1
- **Database**: PostgreSQL 
- **Cache**: Redis
- **Frontend**: HTML5, CSS3, JavaScript
- **Server**: Nginx, Gunicorn
- **Deployment**: Kubernetes
- **CI/CD**: GitHub Actions

## 📁 Project Structure

```
w_tech/
├── account/                    # User auth & profiles
│   ├── static/
│   │   └── css/
│   │       └── account.css    # Account styling
│   ├── templates/
│   ├── admin.py
│   ├── authentication.py
│   ├── forms.py
│   ├── models.py
│   ├── tests.py
│   ├── urls.py
│   └── views.py
├── actions/                    # Activity tracking
│   ├── admin.py
│   ├── models.py
│   ├── tests.py
│   ├── utils.py
│   └── views.py
├── blog/                      # Blog functionality
│   ├── static/
│   │   └── css/
│   │       ├── blog.css      # Blog styling
│   │       └── blog-dark.css # Dark mode styling
│   ├── templates/
│   │   └── blog/
│   │       ├── base.html
│   │       └── post/
│   └── views.py
├── core/                      # Website core
│   ├── static/
│   │   ├── css/
│   │   │   ├── dark-mode.css # Dark theme
│   │   │   ├── main.css     # Main styling
│   │   │   └── normalize.css # CSS reset
│   │   └── js/
│   │       ├── main.js      # Core JavaScript
│   │       └── theme.js     # Theme switcher
│   └── templates/
│       └── core/
│           ├── about.html
│           ├── base.html
│           ├── index.html
│           └── projects.html
├── images/                    # Image handling
│   ├── static/
│   │   └── css/
│   │       └── images.css    # Image gallery styling
│   └── templates/
│       └── images/
│           └── base.html
├── static/                    # Static files
├── wielandtech/              # Project settings
├── .env                      # Environment variables
├── Dockerfile                # Docker image for CI/CD
├── manage.py                 # Django CLI
├── requirements.txt          # Python dependencies
└── README.md                 # Documentation
```

## 🚀 Getting Started

## 🐳 Container Images

GitHub Actions builds the Docker image with repo-scoped homelab runners.

- Pushes to `main` publish production tags like `20260529-143000-abc1234`.
- Pushes to non-main branches publish shared dev tags like `dev-20260529-143000-abc1234`.
- Same-repository pull requests publish review-app tags like `pr-123-abc1234`; fork pull requests build for validation without pushing to GHCR.

The homelab Flux Image Automation watches the `dev-*` tags for the shared `website-dev` environment.

1. Clone repository:
```bash
git clone https://github.com/wielandtech-labs/w_tech.git
cd wielandtech
```

2. Create virtual environment:
```bash
python -m venv venv
venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Configure environment variables in `.env`:
```env
# Django settings
DJANGO_SECRET_KEY='your-secret-key'
DEBUG=True
ALLOWED_HOSTS=your-domain.com,www.your-domain.com,your-ip-address

# Database configuration
DATABASE_NAME=your_db_name
DATABASE_USER=your_db_user
DATABASE_PASSWORD="your-password"
DATABASE_HOST=db
DATABASE_PORT=5432

# Email settings
EMAIL_HOST=mail.your-domain.com
EMAIL_HOST_USER=no-reply@your-domain.com
EMAIL_PASSWORD="your-email-password"
EMAIL_PORT=465
EMAIL_USE_SSL=True

# GitHub webhook
GITHUB_WEBHOOK_SECRET=your-webhook-secret

# Social auth credentials
SOCIAL_AUTH_FACEBOOK_KEY="your-facebook-key"
SOCIAL_AUTH_FACEBOOK_SECRET="your-facebook-secret"

SOCIAL_AUTH_GOOGLE_OAUTH2_KEY="your-google-oauth2-key"
SOCIAL_AUTH_GOOGLE_OAUTH2_SECRET="your-google-oauth2-secret"

# Redis configuration
REDIS_IP="your-redis-ip"
REDIS_KEY="your-redis-key"
REDIS_PORT=6379
REDIS_DB=0
```

5. Run migrations:
```bash
python manage.py migrate
```

6. Start development server:
```bash
python manage.py runserver
```

## 🔧 Development

### Prerequisites
- Python 3.10+
- PostgreSQL 14+
- Redis 6+

### Testing
```bash
# Run tests
python manage.py test

# Run with coverage
coverage run manage.py test
coverage report
```

### Deployment

This application is deployed using Kubernetes in a homelab environment. The deployment configuration is managed separately from this repository.

## 📝 License

[BSD 3-Clause License](LICENSE)

## 📫 Contact

- Website: [wielandtech.com](https://wielandtech.com)
- Email: raphael@wielandtech.com
- GitHub: [@wielandtech](https://github.com/wielandtech)
