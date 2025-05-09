from django.contrib import messages
from venv import logger
from django.contrib.auth.decorators import login_required
from django.contrib.auth import logout
from django.db import IntegrityError
from django.views.decorators.http import require_POST
from django.shortcuts import render, redirect,get_object_or_404
from django.urls import reverse, reverse_lazy
from django.http import Http404, HttpResponse, JsonResponse
from merchant_app.models import Order
from .models import Rider, OrderAssignment, RiderBankAccount, RiderEarning
from .forms import BankDetailsForm, RiderPasswordResetForm, RiderRegistrationForm, RiderLoginForm
from django.contrib.auth.views import LoginView
import logging
from django.db import transaction
from datetime import datetime, timedelta
from django.db.models import Sum
from merchant_app.models import Restaurant 
from user_app.models import Order
from django.utils import timezone
from django.views.generic import TemplateView
from django.contrib.auth.views import (
    PasswordResetView as BasePasswordResetView,
    PasswordResetDoneView as BasePasswordResetDoneView,
    PasswordResetConfirmView as BasePasswordResetConfirmView,
    PasswordResetCompleteView as BasePasswordResetCompleteView
)

logger = logging.getLogger(__name__)


@login_required
def rider_dashboard(request):
    try:
        rider = request.user.rider
        if not hasattr(rider, 'total_assignments'):
            rider.total_assignments = 0
        if not hasattr(rider, 'accepted_assignments'):
            rider.accepted_assignments = 0
            
        acceptance_rate = rider.get_acceptance_rate()

        print(f"Debug: Found rider - Rider ID: {rider.id}, Available: {rider.is_available}, Approved: {rider.is_approved}")
    except Rider.DoesNotExist:
        print("Debug: No rider profile found for the logged-in user.")
        messages.error(request, "Rider profile not found. Please register or contact support.")
        return redirect('rider:registration') 

    active_orders = OrderAssignment.objects.filter(
        rider=rider,
        status__in=['pending', 'accepted'],  
        order__status__in=['ready', 'out_for_delivery']
    ).select_related('order', 'order__restaurant') 

    print(f"Debug: Found {active_orders.count()} active orders for rider {rider.id} with status in ['pending', 'accepted'] and order status in ['ready', 'out_for_delivery'].")
    

    completed_orders = OrderAssignment.objects.filter(
        rider=rider,
        status='delivered' 
    ).order_by('-updated_at')[:5].select_related('order', 'order__restaurant')

    context = {
        'rider': rider,
        'active_orders': active_orders,
        'completed_orders': completed_orders,
        'total_earnings': rider.get_total_earnings(),
        'total_orders': rider.get_total_orders_completed(),
        'acceptance_rate': rider.get_acceptance_rate(),
        'weekly_earnings': get_weekly_earnings(rider),
        'acceptance_stats': {
            'accepted': rider.accepted_assignments,
            'total': rider.total_assignments
        }
    }
    return render(request, 'rider_app/dashboard.html', context)

def get_weekly_earnings(rider):
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=7)
    
    earnings = (RiderEarning.objects
                .filter(rider=rider, date__range=[start_date, end_date])
                .values('date')
                .annotate(daily_earnings=Sum('total_earnings'))
                .order_by('date'))
    
    dates = [start_date + timedelta(days=i) for i in range(7)]
    
    earnings_dict = {e['date']: float(e['daily_earnings']) for e in earnings}
    
    return [{
        'date': date,
        'earnings': earnings_dict.get(date, 0)
    } for date in dates]




@require_POST
def update_availability(request):
    if not request.user.is_authenticated:
        return JsonResponse({'status': 'error', 'message': 'Authentication required'}, status=401)
    
    try:
        rider = request.user.rider
        rider.is_available = not rider.is_available
        rider.save()
        
        return JsonResponse({
            'status': 'success',
            'is_available': rider.is_available,
            'button_text': 'Available' if rider.is_available else 'Not Available',
            'button_class': 'bg-green-500' if rider.is_available else 'bg-red-500'
        })
    except Rider.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Rider profile not found'}, status=404)
    except Exception as e:
        return JsonResponse({
        'status': 'success',
        'is_available': rider.is_available,
        'button_text': 'Available' if rider.is_available else 'Not Available',
        'button_class': 'bg-green-500' if rider.is_available else 'bg-red-500'
    })


@require_POST
@login_required
def accept_order(request, order_id):
    try:
        rider = request.user.rider
        assignment = OrderAssignment.objects.get(
            order_id=order_id,
            rider=rider,
            status='pending'
        )
        assignment.status = 'accepted'
        assignment.accepted_at = timezone.now()
        assignment.save()

        OrderAssignment.objects.filter(
            order_id=order_id
        ).exclude(rider=rider).update(status='rejected')  # <-- Key change

        order = assignment.order
        order.status = 'out_for_delivery'
        order.save()

        return JsonResponse({'status': 'success'})
    except Exception as e:
        logger.error(f"Error accepting order: {str(e)}")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

def rider_registration(request):
    if request.method == 'POST':
        form = RiderRegistrationForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                with transaction.atomic():
                    user = form.save(commit=False)
                    user.save()
                    
                    Rider.objects.create(
                        user=user,
                        phone=form.cleaned_data['phone'],
                        gender=form.cleaned_data['gender'],
                        aadhar_number=form.cleaned_data['aadhar_number'],
                        driving_license=form.cleaned_data['driving_license'],
                        address=form.cleaned_data['address'],
                        area=form.cleaned_data['area'],
                        pincode=form.cleaned_data['pincode'],
                        profile_photo=form.cleaned_data['profile_photo'],
                        aadhar_front=form.cleaned_data['aadhar_front'],
                        license_copy=form.cleaned_data['license_copy'],
                        is_approved=False
                    )
                
                messages.success(request, "Registration successful! Please wait for approval.")
                return redirect('rider:registration_success')
                
            except Exception as e:
                logger.error(f"Registration error: {str(e)}", exc_info=True)
                messages.error(request, "Registration failed. Please try again.")
        else:
            messages.error(request, "Please correct the errors below.")
    
    else:  
        form = RiderRegistrationForm()
    
    return render(request, 'registration.html', {'form': form})


def registration_success(request):
    return render(request, 'registration_success.html')



class RiderLoginView(LoginView):
    form_class = RiderLoginForm
    template_name = 'rider-login.html'
    def get_success_url(self):
        return reverse('rider:dashboard')
    

@login_required
def bank_details(request):
    bank_accounts = request.user.rider.bank_accounts.all()
    
    if request.method == 'POST':
        form = BankDetailsForm(request.POST)
        if form.is_valid():
            bank_account = form.save(commit=False)
            bank_account.rider = request.user.rider
            if not bank_accounts.exists():
                bank_account.is_primary = True
            bank_account.save()
            messages.success(request, "Bank account added successfully")
            return redirect('rider:bank_details')
    else:
        form = BankDetailsForm()
    
    return render(request, 'rider_app/bank_details_list.html', {
        'form': form,
        'bank_accounts': bank_accounts,
        'rider': request.user.rider
    })


def rider_logout(request):
    logout(request)
    return redirect('rider:rider-login')

@login_required
def rider_earnings(request):
    try:
        rider = request.user.rider
        earnings = RiderEarning.objects.filter(rider=rider).order_by('-date')[:30]  # Last 30 earnings
        
        context = {
            'rider': rider,
            'earnings': earnings,
            'total_earnings': sum(earning.total_earnings for earning in earnings),
            'total_orders': sum(earning.orders_completed for earning in earnings)
        }
        return render(request, 'rider_app/earnings.html', context)
        
    except Rider.DoesNotExist:
        messages.warning(request, "Please complete your rider registration first")
        return redirect('rider_registration')
    except Exception as e:
        logger.error(f"Earnings view error: {str(e)}")
        messages.error(request, "Unable to load earnings data")
        return redirect('rider:dashboard')
      

@require_POST
@login_required
def mark_delivered(request, order_id):
    try:
        rider = request.user.rider
        assignment = OrderAssignment.objects.get(
            order_id=order_id,
            rider=rider,
            status='accepted'
        )
        
        assignment.status = 'delivered'
        assignment.save()
        
        order = assignment.order
        order.status = 'delivered'
        order.save()
        
        return JsonResponse({'status': 'success'})
        
    except OrderAssignment.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Order not found'}, status=404)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
    


@login_required
def bank_details_list(request): 
    try:
        rider = request.user.rider
        bank_accounts = RiderBankAccount.objects.filter(rider=rider)
        
        if request.method == 'POST':
           
            form = BankDetailsForm(request.POST, rider=rider)
            if form.is_valid():
                bank_account = form.save(commit=False)
                bank_account.rider = rider
                if not bank_accounts.exists():
                    bank_account.is_primary = True
                bank_account.save()
                messages.success(request, "✅ Bank account added successfully!")
                return redirect('rider:bank_details_list') 
            else:
                messages.error(request, "❌ Please correct the errors below.")
        else:
            form = BankDetailsForm(rider=rider)
        
        return render(request, 'rider_app/bank_details_list.html', { 
            'form': form,
            'rider': rider,
            'bank_accounts': bank_accounts
        })
        
    except Rider.DoesNotExist:
        messages.warning(request, "Please complete your rider registration first")
        return redirect('rider:registration')
    

@login_required
@require_POST 
def delete_bank_account(request, account_id):
    try:
        rider = request.user.rider
        bank_account = get_object_or_404(RiderBankAccount, id=account_id, rider=rider)

        if bank_account.is_primary:
            messages.error(request, "❌ You cannot delete your primary bank account.")
        else:
            bank_account.delete()
            messages.success(request, "✅ Bank account deleted successfully.")
        
    except Rider.DoesNotExist:
        messages.error(request, "Rider profile not found.")
    except RiderBankAccount.DoesNotExist:
        messages.error(request, "Bank account not found.")
    
        
    return redirect('rider:bank_details_list') 

@login_required
@require_POST
def set_primary_bank_account(request, account_id):
    try:
        rider = request.user.rider
        bank_account_to_set_primary = get_object_or_404(RiderBankAccount, id=account_id, rider=rider)
        
        bank_account_to_set_primary.is_primary = True
        bank_account_to_set_primary.save()
        
        messages.success(request, f"✅ Account {bank_account_to_set_primary.account_number} is now your primary account.")
        
    except Rider.DoesNotExist:
        messages.error(request, "Rider profile not found.")
    except RiderBankAccount.DoesNotExist:
        messages.error(request, "Bank account not found.")
        
    return redirect('rider:bank_details_list')


@login_required
def rider_order_detail(request, order_id):
    try:
        rider = request.user.rider  
        assignment = get_object_or_404(OrderAssignment, order_id=order_id, rider=rider)
        order = assignment.order

        if assignment.status != "accepted":
            return render(request, "rider_app/accept_order_prompt.html", {
                "assignment": assignment,
                "order": order,
                "rider": rider  
            })

        return render(request, "rider_app/order_detail.html", {
            "order": order,
            "assignment": assignment,
            "dest_lat": order.dest_lat,
            "dest_lon": order.dest_lon,
            "rider": rider  
        })
        
    except Rider.DoesNotExist:
        messages.error(request, "Rider profile not found")
        return redirect('rider:dashboard')


@require_POST
@login_required
def accept_order_assignment(request, order_id):
    assignment = get_object_or_404(OrderAssignment, order_id=order_id, rider=request.user.rider)

    if assignment.status == "pending": 
        assignment.status = "accepted" 
        assignment.accepted_at = timezone.now() 
        assignment.save() 
        messages.success(request, "Order accepted successfully!")
    elif assignment.status == "accepted":
        messages.info(request, "Order was already accepted.")
    else:
        messages.error(request, f"Order cannot be accepted. Current status: {assignment.status}")

    return redirect('rider:rider_order_detail', order_id=order_id)






#password reset

from mailersend import emails
from django.conf import settings
from django.template.loader import render_to_string

class RiderPasswordResetView(BasePasswordResetView):
    template_name = 'rider_app/password_reset.html'
    email_template_name = 'rider_app/password_reset_email.html'
    subject_template_name = 'rider_app/password_reset_subject.txt'
    success_url = reverse_lazy('rider:password_reset_done')
    form_class = RiderPasswordResetForm

    def form_valid(self, form):
        return super().form_valid(form)

    def send_mail(self, subject_template_name, email_template_name,
                  context, from_email, to_email, html_email_template_name=None):
        subject = render_to_string(subject_template_name, context)
        subject = ''.join(subject.splitlines())
        body = render_to_string(email_template_name, context)

        mailer = emails.NewEmail(settings.MAILERSEND_API_KEY)
        
        mail_body = {
            "personalization": [
                {
                    "email": to_email,
                    "data": {
                        "username": context['user'].username,
                        "reset_link": f"{context['protocol']}://{context['domain']}{context['reset_url']}"
                    }
                }
            ]
        }

        mail_from = {
            "email": settings.DEFAULT_FROM_EMAIL,
            "name": "BiteQue Rider Support"
        }

        recipients = [
            {
                "email": to_email,
                "name": context['user'].username
            }
        ]

        mailer.set_mail_from(mail_from, mail_body)
        mailer.set_mail_to(recipients, mail_body)
        mailer.set_subject(subject, mail_body)
        mailer.set_html_content(body, mail_body)

        mailer.send(mail_body)

class RiderPasswordResetDoneView(BasePasswordResetDoneView):
    template_name = 'rider_app/password_reset_done.html'

class RiderPasswordResetConfirmView(BasePasswordResetConfirmView):
    template_name = 'rider_app/password_reset_confirm.html'
    success_url = reverse_lazy('rider:password_reset_complete')

class RiderPasswordResetCompleteView(TemplateView):
    template_name = 'rider_app/password_reset_complete.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['login_url'] = '/rider-login/' 
        return context