from decimal import Decimal
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth import logout
from django.db import IntegrityError
from django.views.decorators.http import require_POST,require_http_methods
from django.shortcuts import render, redirect,get_object_or_404
from django.urls import reverse, reverse_lazy
from django.http import Http404, HttpResponse, HttpResponseBadRequest, JsonResponse
from merchant_app.models import Order
from .models import Rider, OrderAssignment, RiderBankAccount, RiderEarning
from .forms import BankDetailsForm, DeliveryOTPForm, RiderPasswordResetForm, RiderRegistrationForm, RiderLoginForm
from django.contrib.auth.views import LoginView
import logging
from django.db import transaction
from datetime import datetime, timedelta
from django.db.models import Sum,F
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
from django.core.paginator import Paginator
from rider_app import models

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
    except Rider.DoesNotExist:
        messages.error(request, "Rider profile not found. Please register or contact support.")
        return redirect('rider:registration') 

    active_orders = OrderAssignment.objects.filter(
        rider=rider,
        status__in=['pending', 'accepted'],  
        order__status__in=['ready', 'out_for_delivery']
    ).select_related('order', 'order__restaurant') 

    completed_orders = OrderAssignment.objects.filter(
        rider=rider,
        status='delivered' 
    ).order_by('-updated_at')[:5].select_related('order', 'order__restaurant')

    context = {
        'rider': rider,
        'active_orders': active_orders,
        'completed_orders': completed_orders,
        'total_earnings': rider.get_total_earnings(),
        'today_earnings': rider.today_earnings,
        'current_balance': rider.get_current_balance(),
        'weekly_earnings': get_weekly_earnings(rider),
        'total_orders': rider.get_total_orders_completed(),
        'acceptance_rate': rider.get_acceptance_rate(),
        'acceptance_stats': {
                'score': rider.get_acceptance_rate(),
                'response_times': rider.orderassignment_set.filter(
                    status='accepted'
                ).values_list('response_time', flat=True)[:10]
            },
        'earnings': RiderEarning.objects.filter(rider=rider).order_by('-date')[:5],  # Last 5 earnings
        
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
        logger.error(f"Error updating availability: {e}", exc_info=True)
        return JsonResponse({'status': 'error', 'message': 'Unable to update availability'}, status=500)


@require_POST
@login_required
def accept_order(request, order_id):
    try:
        rider = request.user.rider
    except Rider.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Rider profile not found'}, status=404)

    try:
        with transaction.atomic():
            assignment = OrderAssignment.objects.select_for_update().get(
                order_id=order_id,
                rider=rider,
                status='pending'
            )
            assignment.status = 'accepted'
            assignment.accepted_at = timezone.now()
            assignment.save()
            # Side effects (order -> out_for_delivery, PIN generation,
            # rejecting the other riders) are handled by the
            # handle_order_assignment_changes signal inside this transaction.

        return JsonResponse({'status': 'success'})
    except OrderAssignment.DoesNotExist:
        return JsonResponse(
            {'status': 'error', 'message': 'Order is no longer available for acceptance.'},
            status=409
        )
    except IntegrityError:
        # Partial unique constraint: only one accepted assignment per order.
        return JsonResponse(
            {'status': 'error', 'message': 'Order was just accepted by another rider.'},
            status=409
        )
    except Exception as e:
        logger.error(f"Error accepting order: {e}", exc_info=True)
        return JsonResponse({'status': 'error', 'message': 'Unable to accept order.'}, status=500)

def rider_registration(request):
    if request.method == 'POST':
        form = RiderRegistrationForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                with transaction.atomic():
                    user = form.save(commit=False)
                    full_name_parts = form.cleaned_data['full_name'].split()
                    user.first_name = full_name_parts[0] if full_name_parts else ''
                    user.last_name = ' '.join(full_name_parts[1:]) if len(full_name_parts) > 1 else ''
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
                        aadhar_back=form.cleaned_data['aadhar_back'],
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
        rider = get_object_or_404(Rider, user=request.user)
        weekly_orders = OrderAssignment.objects.filter(
            rider=rider,
            status='delivered',
            updated_at__gte=timezone.now() - timedelta(days=7)
        ).select_related('order').order_by('-updated_at')
        earnings = RiderEarning.objects.filter(rider=rider).order_by('-date')
        transactions = rider.transaction_set.all().order_by('-transaction_date')[:20]
        paginator = Paginator(transactions, 10)  
        page_number = request.GET.get('page')
        page_obj = paginator.get_page(page_number)
        total_earnings = sum(earning.total_earnings for earning in earnings)
        payments = rider.transaction_set.filter(
            transaction_type='payment',
            processed=True
        ).aggregate(Sum('amount'))['amount__sum'] or 0
        
        pending = rider.transaction_set.filter(
            transaction_type='pending',
            processed=False
        ).aggregate(Sum('amount'))['amount__sum'] or 0
        
        context = {
            'rider': rider,
            'weekly_orders': weekly_orders,
            'earnings': earnings,
            'transactions': transactions,
            'total_earnings': rider.get_total_earnings(),
            'current_balance': rider.get_current_balance(),
            'total_orders': weekly_orders.count(),
        }
        return render(request, 'rider_app/earnings.html', context)
        
    except Exception as e:
        logger.error(f"Earnings error: {str(e)}", exc_info=True)
        messages.error(request, "Error loading earnings page")
        return redirect('rider:dashboard')
      
    



@login_required
@require_http_methods(["GET", "POST"])
def mark_delivered(request, order_id):
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    try:
        rider = request.user.rider
        assignment = get_object_or_404(
            OrderAssignment,
            order_id=order_id,
            rider=rider,
            status='accepted'
        )
        order = assignment.order

        if not (order.status == 'out_for_delivery' and order.delivery_pin):
            message = "Order not ready for PIN or PIN not set."
            if is_ajax:
                return JsonResponse({'status': 'error', 'message': message}, status=400)
            messages.error(request, message)
            return redirect('rider:rider_order_detail', order_id=order.id)

        if request.method == 'POST':
            form = DeliveryOTPForm(request.POST)
            if form.is_valid():
                entered_otp = form.cleaned_data['otp']

                if order.delivery_pin_is_expired():
                    message = ("This PIN has expired. Ask the customer to open "
                               "their order page for a new PIN.")
                    logger.warning(
                        "Expired delivery PIN presented for order %s by rider %s.",
                        order.id, rider.id,
                    )
                    if is_ajax:
                        return JsonResponse({'status': 'error', 'message': message, 'field_errors': {'otp': [message]}}, status=400)
                    messages.error(request, message)
                elif order.is_delivery_pin_valid(entered_otp):
                    try:
                        with transaction.atomic():
                            # Lock the assignment so a double-submitted request
                            # cannot earn twice for the same delivery.
                            locked = OrderAssignment.objects.select_for_update().get(
                                pk=assignment.pk, status='accepted'
                            )
                            order.refresh_from_db(fields=['status'])
                            if order.status != 'out_for_delivery':
                                raise ValueError("order_not_out_for_delivery")

                            locked.status = 'delivered'
                            locked.save()

                            restaurant = order.restaurant
                            distance_km = order.distance_km  # Use the already stored distance
                            distance_earning = order.distance_earning  # Use the already stored earning

                            order_total = order.total
                            if order_total <= 200:
                                commission_rate = Decimal('0.10')
                            elif order_total <= 400:
                                commission_rate = Decimal('0.06')
                            elif order_total <= 1000:
                                commission_rate = Decimal('0.04')
                            elif order_total <= 2000:
                                commission_rate = Decimal('0.02')
                            elif order_total <= 4000:
                                commission_rate = Decimal('0.01')
                            else:
                                commission_rate = Decimal('0.00')

                            commission_earning = order_total * commission_rate
                            total_earning = distance_earning + commission_earning

                            order.commission = commission_earning
                            order.total_earning = total_earning
                            order.save(update_fields=['commission', 'total_earning'])

                            rider.today_earnings += total_earning
                            rider.save(update_fields=['today_earnings'])

                            today = timezone.now().date()
                            rider_earning, created = RiderEarning.objects.get_or_create(
                                rider=rider,
                                date=today,
                                defaults={
                                    'total_earnings': total_earning,
                                    'orders_completed': 1,
                                    'distance_km': distance_km,
                                    'distance_earning': distance_earning,
                                    'commission_earning': commission_earning
                                }
                            )
                            if not created:
                                rider_earning.total_earnings += total_earning
                                rider_earning.orders_completed += 1
                                rider_earning.distance_km += distance_km
                                rider_earning.distance_earning += distance_earning
                                rider_earning.commission_earning += commission_earning
                                rider_earning.save()
                    except OrderAssignment.DoesNotExist:
                        message = "This order has already been marked as delivered."
                        if is_ajax:
                            return JsonResponse({'status': 'error', 'message': message}, status=409)
                        messages.error(request, message)
                        return redirect('rider:dashboard')
                    except ValueError:
                        message = "Order is not in a deliverable state."
                        if is_ajax:
                            return JsonResponse({'status': 'error', 'message': message}, status=400)
                        messages.error(request, message)
                        return redirect('rider:dashboard')

                    if is_ajax:
                        return JsonResponse({
                            'status': 'success',
                            'message': f"Order #{order.id} marked as delivered successfully!",
                            'order_id': order.id
                        })
                    messages.success(request, f"Order #{order.id} marked as delivered successfully!")
                    return redirect('rider:dashboard')
                else:
                    if order.register_delivery_pin_failure():
                        message = ("Too many incorrect PIN attempts. Ask the "
                                   "customer for a new PIN.")
                    else:
                        message = "Incorrect PIN. Please confirm with the customer and try again."
                    logger.warning(
                        "Failed PIN attempt for order %s by rider %s.",
                        order.id, rider.id,
                    )
                    if is_ajax:
                        return JsonResponse({'status': 'error', 'message': message, 'field_errors': {'otp': [message]}}, status=400)
                    messages.error(request, message)
            else:
                if is_ajax:
                    return JsonResponse({'status': 'error', 'message': 'Invalid input.', 'field_errors': form.errors.get_json_data()}, status=400)
                messages.error(request, "Invalid input. Please check the PIN format.")

        form = DeliveryOTPForm(request.POST or None)
        return render(request, 'rider_app/mark_delivered_otp.html', {
            'form': form,
            'order': order,
            'assignment': assignment
        })

    except OrderAssignment.DoesNotExist:
        message = "Order assignment not found or not in 'accepted' state."
        if is_ajax:
            return JsonResponse({'status': 'error', 'message': message}, status=404)
        messages.error(request, message)
        return redirect('rider:dashboard')

    except Http404:
        message = "Order assignment not found or not in 'accepted' state."
        if is_ajax:
            return JsonResponse({'status': 'error', 'message': message}, status=404)
        messages.error(request, message)
        return redirect('rider:dashboard')

    except Exception as e:
        logger.error(f"Error in mark_delivered view for order {order_id}: {str(e)}", exc_info=True)
        message = "An unexpected error occurred."
        if is_ajax:
            return JsonResponse({'status': 'error', 'message': message}, status=500)
        messages.error(request, message)
        return redirect('rider:dashboard')



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
                "rider": rider,
                "delivery_fee": assignment.order.distance_earning
            })

        return render(request, "rider_app/order_detail.html", {
            "order": order,
            "assignment": assignment,
            "dest_lat": order.dest_lat,
            "dest_lon": order.dest_lon,
            "rider": rider,
            "delivery_fee": order.distance_earning
        })
        
    except Rider.DoesNotExist:
        messages.error(request, "Rider profile not found")
        return redirect('rider:dashboard')


@require_POST
@login_required
def accept_order_assignment(request, order_id):
    try:
        rider = request.user.rider
    except Rider.DoesNotExist:
        messages.error(request, "Rider profile not found")
        return redirect('rider:dashboard')

    try:
        with transaction.atomic():
            assignment = OrderAssignment.objects.select_for_update().get(
                order_id=order_id,
                rider=rider
            )

            if assignment.status == "pending":
                assignment.status = "accepted"
                assignment.accepted_at = timezone.now()
                assignment.save()
                messages.success(request, "Order accepted successfully!")
            elif assignment.status == "accepted":
                messages.info(request, "Order was already accepted.")
            else:
                messages.error(request, f"Order cannot be accepted. Current status: {assignment.status}")
    except OrderAssignment.DoesNotExist:
        messages.error(request, "Order assignment not found.")
    except IntegrityError:
        messages.error(request, "Order was just accepted by another rider.")
    except Exception as e:
        logger.error(f"Error accepting assignment for order {order_id}: {e}", exc_info=True)
        messages.error(request, "Unable to accept order.")

    return redirect('rider:rider_order_detail', order_id=order_id)






#password reset

from mailersend import emails
from django.conf import settings
from django.template.loader import render_to_string


from django.urls import reverse_lazy
from django.template.loader import render_to_string
from rider_app.brevo_helper import send_brevo_email

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
        html_content = render_to_string(email_template_name, context)
        
        
        user = context['user']
        send_brevo_email(
            subject=subject,
            html_content=html_content,
            recipient_email=user.email,
            recipient_name=user.username
        )


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
    
@login_required
def earning_details(request, earning_id):
    try:
        earning = RiderEarning.objects.get(
            id=earning_id,
            rider=request.user.rider  
        )
        
        return JsonResponse({
            'status': 'success',
            'distance_km': float(earning.distance_km) if hasattr(earning, 'distance_km') else 0,
            'distance_earning': float(earning.distance_earning) if hasattr(earning, 'distance_earning') else 0,
            'commission_earning': float(earning.commission_earning) if hasattr(earning, 'commission_earning') else 0,
            'total_earning': float(earning.total_earnings),
            'orders_completed': earning.orders_completed,
            'date': earning.date.strftime("%b %d, %Y")
        })
    except RiderEarning.DoesNotExist:
        return JsonResponse({
            'status': 'error',
            'message': 'Earning record not found'
        }, status=404)
    


@login_required
def order_earning_details(request, order_id):
    try:
        order = Order.objects.get(
            id=order_id,
            assignments__rider=request.user.rider,
            assignments__status='delivered'
        )
        
        required_fields = [
            'distance_km', 'distance_earning',
            'commission', 'total_earning',
            'restaurant', 'customer_name'
        ]
        for field in required_fields:
            if not hasattr(order, field):
                raise AttributeError(f"Order missing {field} field")

        return JsonResponse({
            'status': 'success',
            'date': order.created_at.strftime("%b %d, %Y"),
            'order_id': order.id,
            'distance_km': float(order.distance_km),
            'distance_earning': float(order.distance_earning),
            'commission_earning': float(order.commission),
            'total_earning': float(order.total_earning),
            'restaurant': order.restaurant.name,
            'customer': order.customer_name,
            'delivery_address': order.delivery_address
        })
        
    except Order.DoesNotExist:
        return JsonResponse({
            'status': 'error', 
            'message': 'Order not found or not delivered by you'
        }, status=404)
        
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)
    

