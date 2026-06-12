# Security Configuration

This document outlines the security measures implemented for the WielandTech Django application.

## 🔒 Security Features

### 1. Admin Access Restriction

**Admin panel (`/admin/`) is restricted to internal network only.**

- ✅ **Accessible via**: `http://wielandtech.k8s.local/admin/`
- ❌ **Blocked on**: `https://wielandtech.com/admin/`, `https://www.wielandtech.com/admin/`

**Implementation**: Custom middleware `RestrictAdminMiddleware` checks the request host and blocks public admin access.

### 2. HTTPS Security Headers

When `DEBUG=False`, the following security features are enabled:

#### Cookie Security
- `CSRF_COOKIE_SECURE = True` - CSRF cookies only sent over HTTPS
- `SESSION_COOKIE_SECURE = True` - Session cookies only sent over HTTPS
- **Internal-host exception**: `InternalAdminCookieMiddleware` strips the
  `Secure` flag from the session/CSRF cookies for plain-HTTP requests on the
  internal admin hosts (`wielandtech.k8s.local`, `127.0.0.1`, `localhost`).
  Without this, admin login at `http://wielandtech.k8s.local/admin/` fails
  CSRF verification because browsers never send `Secure` cookies over HTTP.
  Public hosts keep fully `Secure` cookies.
- `SESSION_COOKIE_HTTPONLY = True` - JavaScript cannot access session cookies
- `CSRF_COOKIE_HTTPONLY = True` - JavaScript cannot access CSRF cookies
- `SESSION_COOKIE_SAMESITE = 'Lax'` - CSRF protection
- `CSRF_COOKIE_SAMESITE = 'Lax'` - CSRF protection

#### HTTP Strict Transport Security (HSTS)
- `SECURE_HSTS_SECONDS = 31536000` - 1 year HSTS policy
- `SECURE_HSTS_INCLUDE_SUBDOMAINS = True` - Apply to all subdomains
- `SECURE_HSTS_PRELOAD = True` - Eligible for browser preload lists

#### Additional Headers
- `X-Content-Type-Options: nosniff` - Prevent MIME sniffing
- `X-Frame-Options: DENY` - Prevent clickjacking
- `X-XSS-Protection: 1; mode=block` - Enable XSS filtering
- `Referrer-Policy: strict-origin-when-cross-origin` - Control referrer information
- `Content-Security-Policy` - Restrict resource loading (public domains only)

### 3. File Upload Limits

- Maximum upload size: 10MB
- Prevents denial-of-service attacks via large file uploads

### 4. Password Validation

Strong password requirements enforced:
- User attribute similarity check
- Minimum length validation
- Common password check
- Numeric-only password prevention

### 5. CSRF Protection

- Django's CSRF middleware enabled
- Trusted origins configured for cross-origin requests
- SameSite cookie attributes set

## 🧪 Testing Security

### Test Admin Access Restriction

**From Internal Network (should work):**
```bash
# From within your homelab
curl -I http://wielandtech.k8s.local/admin/
# Expected: 200 OK or 302 redirect to login
```

**From Public Internet (should be blocked):**
```bash
# From anywhere
curl -I https://wielandtech.com/admin/
# Expected: 403 Forbidden
```

### Test Public Website Access

**Public pages should work normally:**
```bash
curl -I https://wielandtech.com/
curl -I https://wielandtech.com/blog/
curl -I https://wielandtech.com/account/login/
# Expected: 200 OK
```

### Test Security Headers

```bash
curl -I https://wielandtech.com/ | grep -E 'Strict-Transport|X-Frame|X-Content|CSP'
```

Expected headers:
```
Strict-Transport-Security: max-age=31536000; includeSubDomains; preload
X-Frame-Options: DENY
X-Content-Type-Options: nosniff
Content-Security-Policy: default-src 'self'; ...
```

## 🔐 Admin Access Methods

### Method 1: SSH Tunnel (Recommended)

From your local machine, create an SSH tunnel to your homelab:

```bash
# Create tunnel
ssh -L 8080:wielandtech.k8s.local:80 user@homelab-server

# Access admin via tunnel
http://localhost:8080/admin/
```

### Method 2: VPN

Connect to your homelab VPN (if configured), then access:
```
http://wielandtech.k8s.local/admin/
```

### Method 3: Direct Internal Access

From within your homelab network:
```
http://wielandtech.k8s.local/admin/
```

## 🚨 Security Checklist

Before deploying to production:

- [ ] Set `DEBUG = False` in production environment
- [ ] Use strong `SECRET_KEY` (stored in Kubernetes secret)
- [ ] Verify admin access is blocked from public domains
- [ ] Confirm HTTPS is enforced for all public traffic
- [ ] Test CSRF protection is working
- [ ] Verify security headers are present
- [ ] Review Django security deployment checklist: `python manage.py check --deploy`
- [ ] Enable Django's security logging
- [ ] Set up monitoring for failed login attempts
- [ ] Configure rate limiting in NGINX (already done on VPS)

## 📝 Additional Recommendations

### 1. Consider Additional Admin Protection

For even more security, consider:

```python
# In wielandtech/middleware.py, add IP whitelist:
ALLOWED_ADMIN_IPS = [
    '192.168.70.0/24',  # Your homelab network
]
```

### 2. Enable Django Admin Two-Factor Authentication

Install `django-otp` for 2FA on admin login:

```bash
pip install django-otp qrcode
```

### 3. Set Up Security Monitoring

Monitor for:
- Failed admin login attempts
- 403 Forbidden responses from admin URLs
- Unusual traffic patterns
- File upload attempts

### 4. Regular Security Updates

```bash
# Check for security updates regularly
pip list --outdated
python manage.py check --deploy
```

## 🔄 Deployment

After making security changes:

1. **Commit changes**:
```bash
cd /path/to/w_tech
git add wielandtech/middleware.py wielandtech/settings.py
git commit -m "feat(security): Restrict admin to internal network only"
git push origin main
```

2. **Wait for GitHub Actions** to build and deploy the new image to your cluster (automatic via GitOps).

3. **Verify deployment**:
```bash
kubectl get pods -n website
kubectl logs -n website <pod-name>
```

4. **Test restrictions**:
```bash
# Should be blocked
curl -I https://wielandtech.com/admin/

# Should work
curl -I http://wielandtech.k8s.local/admin/
```

## 📚 Resources

- [Django Security Documentation](https://docs.djangoproject.com/en/stable/topics/security/)
- [OWASP Django Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Django_Security_Cheat_Sheet.html)
- [Mozilla Web Security Guidelines](https://infosec.mozilla.org/guidelines/web_security)

