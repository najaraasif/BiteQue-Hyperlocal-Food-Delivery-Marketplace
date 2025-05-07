from django.contrib import messages
from venv import logger
from django.contrib.auth.decorators import login_required
from django.contrib.auth import logout
from django.db import IntegrityError
from django.views.decorators.http import require_POST
from django.shortcuts import render, redirect,get_object_or_404
from django.urls import reverse
from django.http import Http404, HttpResponse, JsonResponse
from merchant_app.models import Order
from .models import Rider, OrderAssignment, RiderBankAccount, RiderEarning
from .forms import BankDetailsForm, RiderRegistrationForm, RiderLoginForm
from django.contrib.auth.views import LoginView
import logging
from django.db import transaction
from datetime import datetime, timedelta
from django.db.models import Sum
from merchant_app.models import Restaurant 
from user_app.models import Order
from django.utils import timezone

logger = logging.getLogger(__name__)

@login_required
def rider_dashboard(request):
    try:
        rider = request.user.rider
        print(f"Debug: Found rider - Available: {rider.is_available}, Approved: {rider.is_approved}")  # Debug
    except Rider.DoesNotExist:
        print("Debug: No rider profile found")  # Debug
        return redirect('rider:registration')  # Redirect if no rider profile
    
    # Get active and completed orders
    active_orders = OrderAssignment.objects.filter(
            rider=rider,
        status__in=['PENDING', 'ACCEPTED'],  # Only show these
        order__status__in=['ready', 'out_for_delivery']
    )
        
    print(f"Debug: Found {active_orders.count()} active orders")  # Debug
    
    completed_orders = OrderAssignment.objects.filter(
        rider=rider,
        status='DELIVERED'
    ).order_by('-updated_at')[:5]
    
    context = {
        'rider': rider,  # Make sure this is included
        'active_orders': active_orders,
        'completed_orders': completed_orders,
        'total_earnings': rider.get_total_earnings(),
        'total_orders': rider.get_total_orders_completed(),
        'acceptance_rate': rider.get_acceptance_rate(),
        'weekly_earnings': get_weekly_earnings(rider),  # Implement this function
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
    
    # Create a list of all dates in the period
    dates = [start_date + timedelta(days=i) for i in range(7)]
    
    # Map earnings to dates
    earnings_dict = {e['date']: float(e['daily_earnings']) for e in earnings}
    
    return [{
        'date': date,
        'earnings': earnings_dict.get(date, 0)
    } for date in dates]

@login_required
def rider_earnings(request):
    try:
        rider = request.user.rider
        earnings = RiderEarning.objects.filter(rider=rider).order_by('-date')
        
        # Calculate summary stats
        total_earnings = earnings.aggregate(total=Sum('total_earnings'))['total'] or 0
        total_orders = earnings.aggregate(total=Sum('orders_completed'))['total'] or 0
        
        # Weekly breakdown
        weekly_earnings = get_weekly_earnings(rider)  # Reuse your existing function
        
        context = {
            'earnings': earnings,
            'total_earnings': total_earnings,
            'total_orders': total_orders,
            'weekly_earnings': weekly_earnings,
            'current_balance': rider.get_total_earnings(),  # From your model
        }
        return render(request, 'rider_app/earnings.html', context)
        
    except Rider.DoesNotExist:
        messages.warning(request, "Please complete your rider registration")
        return redirect('rider:registration')



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
            status='PENDING'
        )
        assignment.status = 'ACCEPTED'
        assignment.accepted_at = timezone.now()
        assignment.save()

        # Reject all other assignments for this order
        OrderAssignment.objects.filter(
            order_id=order_id
        ).exclude(rider=rider).update(status='REJECTED')  # <-- Key change

        # Update order status
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
    
    else:  # GET request
        form = RiderRegistrationForm()
    
    # This return statement was missing for GET requests
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
            status='ACCEPTED'
        )
        
        assignment.status = 'DELIVERED'
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
def bank_details_list(request): # Renamed from bank_details
    try:
        rider = request.user.rider
        bank_accounts = RiderBankAccount.objects.filter(rider=rider)
        
        if request.method == 'POST':
            # This view will now primarily handle adding new accounts
            # Setting primary and deleting will be separate actions/views
            form = BankDetailsForm(request.POST, rider=rider)
            if form.is_valid():
                bank_account = form.save(commit=False)
                bank_account.rider = rider
                # If no other bank accounts exist, make this one primary
                if not bank_accounts.exists():
                    bank_account.is_primary = True
                bank_account.save()
                messages.success(request, "✅ Bank account added successfully!")
                return redirect('rider:bank_details_list') # Updated redirect
            else:
                messages.error(request, "❌ Please correct the errors below.")
        else:
            form = BankDetailsForm(rider=rider)
        
        return render(request, 'rider_app/bank_details_list.html', { # New template name suggested
            'form': form,
            'rider': rider,
            'bank_accounts': bank_accounts
        })
        
    except Rider.DoesNotExist:
        messages.warning(request, "Please complete your rider registration first")
        return redirect('rider:registration')
    # except Exception as e: # Generic exception handling might hide specific issues
    #     messages.error(request, "Error managing bank details")
    #     return redirect('rider:dashboard')

@login_required
@require_POST # Ensure this view is only accessed via POST
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
    # except Exception as e:
    #     messages.error(request, f"An error occurred: {str(e)}")
        
    return redirect('rider:bank_details_list') # Redirect back to the list

@login_required
@require_POST
def set_primary_bank_account(request, account_id):
    try:
        rider = request.user.rider
        bank_account_to_set_primary = get_object_or_404(RiderBankAccount, id=account_id, rider=rider)
        
        # The model's save method handles unsetting other primary accounts
        bank_account_to_set_primary.is_primary = True
        bank_account_to_set_primary.save()
        
        messages.success(request, f"✅ Account {bank_account_to_set_primary.account_number} is now your primary account.")
        
    except Rider.DoesNotExist:
        messages.error(request, "Rider profile not found.")
    except RiderBankAccount.DoesNotExist:
        messages.error(request, "Bank account not found.")
    # except Exception as e:
    #     messages.error(request, f"An error occurred: {str(e)}")
        
    return redirect('rider:bank_details_list')

@login_required
def get_customer_location(request, order_id):
    try:
        order = Order.objects.get(id=order_id)
        if not order.delivery_latitude or not order.delivery_longitude:
            return JsonResponse({'status': 'error', 'message': 'Location not available'}, status=404)
            
        return JsonResponse({
            'status': 'success',
            'latitude': float(order.delivery_latitude),
            'longitude': float(order.delivery_longitude),
            'address': order.delivery_address
        })
    except Order.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Order not found'}, status=404)