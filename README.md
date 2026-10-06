# 🍔 BiteQue

BiteQue is a hyperlocal food delivery platform I built for local restaurants, customers, and independent delivery riders.

The idea is simple: bring the basic experience people expect from a food delivery app to smaller towns where the big platforms are not always available.

The project started in **Kupwara, Jammu & Kashmir, India**, with a focus on keeping the system practical for local restaurants and delivery partners.

**Live:** https://biteque.onrender.com

[![Python](https://img.shields.io/badge/Python-3.13-blue.svg)](https://www.python.org/)
[![Django](https://img.shields.io/badge/Django-6.1-092E20.svg)](https://www.djangoproject.com/)
[![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-38B2AC.svg)](https://tailwindcss.com/)
[![HTMX](https://img.shields.io/badge/HTMX-3366CC.svg)](https://htmx.org/)
[![Status](https://img.shields.io/badge/Status-Deployed-success.svg)](https://biteque.onrender.com)

---

## What BiteQue Does

BiteQue connects three main users:

- **Customers** can discover restaurants, browse menus, place orders, make online payments, and track their orders.
- **Restaurants** can manage menus, receive orders, update preparation status, and view sales information.
- **Delivery riders** can register, complete KYC, receive delivery assignments, accept orders, verify deliveries with a PIN, and track earnings.
- **Admins** manage approvals, KYC verification, restaurants, riders, bank accounts, and platform operations.

The platform is designed around a local marketplace model rather than trying to copy every feature of a large food delivery company.

---

## 🌐 Live Deployment

The current production deployment runs on Render:

| Component | Details |
|---|---|
| Hosting | Render, Docker deployment |
| Database | PostgreSQL in production |
| Application server | Gunicorn |
| Static files | WhiteNoise |
| Backend | Django 6.1 on Python 3.13 |
| Payments | Razorpay |
| Maps | Google Maps Geocoding API |
| Email | Brevo and MailerSend |
| Local timezone | Asia/Kolkata |

Production secrets and configuration are stored as environment variables. No real API keys or production credentials are committed to the repository.

---

## 🏗️ Architecture

BiteQue is a Django application split into three main application areas:

- `user_app` handles customers, menus, carts, orders, checkout, payments, reviews, and order tracking.
- `merchant_app` handles restaurant onboarding, menus, order management, reports, bank accounts, and merchant support.
- `rider_app` handles rider onboarding, KYC, order assignments, delivery confirmation, and earnings.

At the infrastructure level, the application uses PostgreSQL in production, Docker for deployment, and external services for payments, maps, email, and notifications.

### High-level flow

```text
Customer
   |
   v
Django / user_app
   |
   +----> PostgreSQL
   |
   +----> Razorpay
   |
   +----> Google Maps
   |
   v
Merchant ----> Order preparation ----> Ready
                                      |
                                      v
                                   Riders
                                      |
                                      v
                              Delivery + PIN
                                      |
                                      v
                                  Delivered
                                      |
                                      v
                                  Earnings
```

---

## 👥 User Roles

### Customer

- Browse restaurants
- Browse menus and categories
- Add items to cart
- Place orders
- Pay through Razorpay
- Track order status
- View delivery information
- Rate and review restaurants

### Merchant

- Register a restaurant
- Submit business information
- Manage restaurant profile
- Add and update menu items
- Control item availability
- Accept and prepare orders
- Mark orders ready for pickup
- View order history and sales
- Manage payout information

### Rider

- Register as a delivery partner
- Submit KYC information
- Wait for admin approval
- Toggle availability
- Receive order assignments
- Accept delivery jobs
- Complete deliveries using a customer PIN
- View daily and historical earnings
- Manage payout information

### Admin

- Approve merchants and riders
- Review KYC information
- Manage restaurants
- Review orders and assignments
- Manage payout accounts
- Monitor platform activity

---

## 🔄 Order Lifecycle

An order follows this general flow:

```text
Pending
   ↓
Confirmed
   ↓
Ready
   ↓
Out for Delivery
   ↓
Delivered
```

When an order becomes ready, available and approved riders can receive an assignment.

Once a rider accepts the order:

1. The assignment becomes accepted.
2. Other pending assignments are rejected.
3. The order moves to `out_for_delivery`.
4. A delivery PIN is generated.
5. The rider must provide the correct PIN to complete the delivery.
6. The order becomes delivered.
7. Rider earnings are calculated and recorded.

---

## ⚙️ Some Engineering Decisions

### 1. Preventing two riders from accepting the same order

This was one of the areas I paid particular attention to because it is easy to get wrong in a delivery system.

BiteQue uses a database constraint that allows only one accepted assignment for an order:

```python
models.UniqueConstraint(
    fields=["order"],
    condition=models.Q(status="accepted"),
    name="unique_accepted_assignment_for_order",
)
```

The application also uses transactions and row locking around important delivery operations.

The goal is simple: two riders should never be able to successfully accept and complete the same delivery.

### 2. Delivery PIN

The delivery PIN is generated using Python's `secrets` module.

The current flow includes:

- PIN expiry
- Maximum incorrect attempts
- PIN invalidation after too many failed attempts
- Constant-time PIN comparison
- PIN clearing after delivery
- PIN reissue when required
- Rider authorization through the accepted assignment

This gives the customer a simple way to confirm that the order reached the right person without relying only on a button press.

### 3. Razorpay payment verification

The browser is not treated as the source of truth for payment success.

The server verifies:

- Razorpay signature
- Razorpay order ID
- Payment ID
- Payment amount
- Currency
- Payment-to-order relationship

Payment confirmation is also handled idempotently so a repeated callback does not create another successful payment record.

### 4. Rider earnings

Rider earnings are based on distance and order value.

The current model uses:

```text
Total Earnings
= Distance Earnings
+ Commission Earnings
```

Distance earnings are calculated using the stored delivery distance, while commission uses a tiered rate based on the order value.

| Order Total | Commission |
|---|---:|
| ₹0 - ₹200 | 10% |
| ₹201 - ₹400 | 6% |
| ₹401 - ₹1,000 | 4% |
| ₹1,001 - ₹2,000 | 2% |
| ₹2,001 - ₹4,000 | 1% |
| Above ₹4,000 | 0% |

The model can be changed later as the business model evolves.

### 5. KYC and manual approval

BiteQue is designed for a local marketplace where trust matters.

Merchants and riders go through manual approval before becoming fully active.

Rider onboarding includes information such as:

- Aadhaar details and documents
- Driving licence
- Profile photo
- Address
- Bank account information

Restaurant onboarding includes business information such as:

- PAN
- GSTIN
- FSSAI information
- Restaurant details
- Bank account information

Sensitive documents are not intended to be publicly accessible.

---

## 🔐 Security and Production Hardening

I have intentionally spent time hardening the application beyond basic Django CRUD functionality.

Current protections include:

- `DEBUG=False` by default
- Production `SECRET_KEY` validation
- Configurable `ALLOWED_HOSTS`
- HTTPS-aware Django configuration
- Secure session and CSRF cookies in production
- HSTS and browser security headers
- Ownership checks for customer, merchant, and rider operations
- Private access controls for sensitive uploaded files
- Path traversal protection for media access
- Database constraints for important uniqueness rules
- Transactional delivery operations
- Server-side payment verification
- Delivery PIN expiry and brute-force protection
- Environment-based API credentials
- HTTP timeouts for external services
- No real credentials committed to the repository

The goal is not to claim that the application is impossible to break. The goal is to make the important business operations fail safely and keep improving the weak points as the platform grows.

---

## 🧪 Testing

The project currently has **73 automated tests** covering areas including:

- Customer and merchant flows
- Order creation and checkout
- Delivery fees
- Rider assignment
- Concurrent delivery actions
- Delivery PIN validation
- PIN expiry and attempt limits
- Razorpay payment verification
- Merchant authorization
- KYC media access
- Form validation
- Configuration-based URLs

Useful commands:

```bash
python manage.py test
python manage.py check
python manage.py check --deploy
python manage.py makemigrations --check --dry-run
```

---

## 💻 Technology Stack

### Backend

- Python 3.13
- Django 6.1
- PostgreSQL
- SQLite for local development

### Frontend

- HTML5
- Tailwind CSS
- HTMX
- JavaScript
- Feather Icons
- Heroicons

### Payments and Services

- Razorpay
- Google Maps Geocoding API
- Brevo
- MailerSend
- Fast2SMS
- WhatsApp Cloud API
- OSRM for route/distance support

### Deployment

- Docker
- Gunicorn
- WhiteNoise
- Render

### Other

- Pillow
- WeasyPrint
- geopy

---

## 📁 Project Structure

```text
BITEQUE/
├── BITEQUE/
│   ├── settings.py
│   ├── urls.py
│   ├── asgi.py
│   └── wsgi.py
│
├── user_app/
│   ├── models.py
│   ├── views.py
│   ├── forms.py
│   ├── signals.py
│   ├── urls.py
│   └── templates/
│
├── merchant_app/
│   ├── models.py
│   ├── views.py
│   ├── forms.py
│   ├── signals.py
│   ├── admin.py
│   ├── urls.py
│   └── templates/
│
├── rider_app/
│   ├── models.py
│   ├── views.py
│   ├── forms.py
│   ├── signals.py
│   ├── utils.py
│   ├── management/
│   ├── urls.py
│   └── templates/
│
├── media/
├── static/
├── logs/
├── Dockerfile
├── requirements.txt
├── manage.py
└── README.md
```

---

## 🚀 Local Setup

### 1. Clone the repository

```bash
git clone https://github.com/najaraasif/BiteQue-Hyperlocal-Food-Delivery-Marketplace.git
cd BiteQue-Hyperlocal-Food-Delivery-Marketplace
```

### 2. Create a virtual environment

Windows PowerShell:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

Linux/macOS:

```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

Create a local `.env` file with the required configuration.

At minimum:

```env
SECRET_KEY=your-secret-key
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
```

For payments, maps, email, SMS, and other integrations, add the relevant credentials from the environment configuration section below.

### 5. Run migrations

```bash
python manage.py migrate
```

### 6. Create an admin account

```bash
python manage.py createsuperuser
```

### 7. Start Django

```bash
python manage.py runserver
```

Open:

```text
http://127.0.0.1:8000/
```

### 8. Run tests

```bash
python manage.py test
```

---

## 🔐 Environment Configuration

The application reads secrets and service configuration from environment variables.

Example:

```env
# Django
SECRET_KEY=your-secret-key
DEBUG=False
ALLOWED_HOSTS=your-domain.onrender.com
CSRF_TRUSTED_ORIGINS=https://your-domain.onrender.com
SITE_URL=https://your-domain.onrender.com

# Database
DATABASE_URL=postgresql://user:password@host:5432/dbname

# Email
EMAIL_HOST=smtp-relay.brevo.com
EMAIL_HOST_USER=your-smtp-user
EMAIL_HOST_PASSWORD=your-smtp-password
DEFAULT_FROM_EMAIL=noreply@your-domain.com
BREVO_API_KEY=your-brevo-api-key

# MailerSend
MAILERSEND_API_KEY=your-mailersend-api-key
MAILERSEND_DOMAIN=your-domain

# Maps
GOOGLE_MAPS_API_KEY=your-google-maps-key

# Razorpay
RAZORPAY_KEY_ID=rzp_test_xxxxxxxx
RAZORPAY_KEY_SECRET=your-razorpay-secret

# SMS
FAST2SMS_API_KEY=your-fast2sms-key

# OneSignal
ONESIGNAL_REST_API_KEY=your-onesignal-key
ONESIGNAL_APP_ID=your-onesignal-app-id
```

For local development, keep `.env` untracked.

Never commit real credentials.

---

## 🗺️ Roadmap

BiteQue already has the core customer, merchant, rider, checkout, payment, and delivery flows in place.

The next improvements are more about scaling the product than building the basic marketplace again.

### Planned

- [ ] Live rider GPS tracking
- [ ] Better rider acceptance-rate incentives
- [ ] Improved merchant analytics
- [ ] More robust payout automation
- [ ] Better notification and messaging flows
- [ ] Stronger observability and production monitoring
- [ ] Further cleanup of older authentication and legacy code

### Already implemented

- [x] Customer ordering flow
- [x] Merchant onboarding
- [x] Rider onboarding and KYC
- [x] Restaurant and menu management
- [x] Rider order assignments
- [x] Delivery PIN verification
- [x] Razorpay checkout
- [x] Server-side payment verification
- [x] Rider earnings
- [x] PDF invoice generation
- [x] Production deployment on Render
- [x] Production security hardening
- [x] Automated test coverage for core flows

---

## 👨‍💻 Team

BiteQue was built by:

- **Mohammad Aasif Najar**
- **Shakir Meer**

The project covers product planning, local market research, merchant and rider onboarding, backend development, frontend development, deployment, and ongoing improvements.

---

## 📌 Why I Built It

BiteQue started with a simple observation: smaller towns also need good local technology, but the solution does not always have to look like a smaller copy of a national platform.

I wanted to build something that could actually work for local restaurants and riders, while also giving me a real project to work through problems like payments, concurrency, KYC, delivery workflows, notifications, deployment, and production security.

There is still a lot I want to improve, but the core marketplace is running and the project has grown far beyond the original idea.

---

## 📄 License

This project is currently maintained as a private project. Contact the repository owner before reusing the code or product assets.
