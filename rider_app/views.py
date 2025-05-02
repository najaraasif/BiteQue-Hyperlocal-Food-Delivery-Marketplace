from django.contrib import messages
from venv import logger
from django.contrib.auth.decorators import login_required
from django.contrib.auth import logout
from django.views.decorators.http import require_POST
from django.shortcuts import render, redirect
from django.urls import reverse
from django.http import Http404, JsonResponse
from merchant_app.models import Order
from .models import Rider, OrderAssignment, RiderEarning
from .forms import BankDetailsForm, RiderRegistrationForm, RiderLoginForm
from django.contrib.auth.views import LoginView
import logging

logger = logging.getLogger(__name__)

@login_required
def rider_dashboard(request):
    try:
        # Check if user has rider profile
        rider = request.user.rider  # Using related_name access
    except Rider.DoesNotExist:
        messages.warning(request, "Please complete your rider registration")
        return redirect('rider:registration')
    except Exception as e:
        logger.error(f"Dashboard error: {str(e)}", exc_info=True)
        messages.error(request, "Unable to load dashboard")
        return redirect('rider:dashboard')  # Try redirecting to self instead of home
    
    # Successful case
    orders = OrderAssignment.objects.filter(rider=rider).select_related('order')
    context = {
        'rider': rider,
        'active_orders': orders.filter(status__in=['ACCEPTED', 'PENDING']),
        'completed_orders': orders.filter(status='DELIVERED'),
        'earnings': RiderEarning.objects.filter(rider=rider).order_by('-date')[:7]
    }
    return render(request, 'rider_app/dashboard.html', context)

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
        order = Order.objects.get(id=order_id)
        assignment = OrderAssignment.objects.get(order=order, rider=request.user.rider)
        
        if assignment.status != 'PENDING':
            return JsonResponse({'status': 'error', 'message': 'Order not in pending state'}, status=400)
            
        assignment.status = 'ACCEPTED'
        assignment.save()
        
        return JsonResponse({'status': 'success'})
    except (Order.DoesNotExist, OrderAssignment.DoesNotExist):
        return JsonResponse({'status': 'error', 'message': 'Order not found'}, status=404)
    except OrderAssignment.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Order not found'}, status=404)

@require_POST
def reject_order(request, order_id):
    if not request.user.is_authenticated:
        return JsonResponse({'status': 'error', 'message': 'Authentication required'}, status=401)
    
    try:
        rider = request.user.rider
        assignment = OrderAssignment.objects.get(order_id=order_id, rider=rider)
        
        if assignment.status != 'PENDING':
            return JsonResponse({'status': 'error', 'message': 'Order cannot be rejected'}, status=400)
        
        assignment.status = 'REJECTED'
        assignment.save()
        
        return JsonResponse({
            'status': 'success', 
            'message': f'Order #{order_id} rejected',
            'order_id': order_id
        })
    except OrderAssignment.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Order not found'}, status=404)

def rider_registration(request):
    if request.method == 'POST':
        form = RiderRegistrationForm(request.POST, request.FILES)
        if form.is_valid():
            user = form.save()
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
                license_copy=form.cleaned_data['license_copy']
            )
            return redirect('registration_success')
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
    try:
        rider = request.user.rider
        
        if request.method == 'POST':
            form = BankDetailsForm(request.POST, instance=rider)
            if form.is_valid():
                form.save()
                messages.success(request, "✅ Bank details updated successfully!")
                return redirect('rider:bank_details')
            else:
                messages.error(request, "❌ Please correct the errors below")
        else:
            form = BankDetailsForm(instance=rider)
        
        return render(request, 'rider_app/bank_details.html', {
            'form': form,
            'rider': rider
        })
        
    except Rider.DoesNotExist:
        messages.warning(request, "Please complete your rider registration first")
        return redirect('rider:registration')
    except Exception as e:
        messages.error(request, "Error updating bank details")
        return redirect('rider:dashboard')


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
      