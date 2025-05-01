from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.urls import reverse
from django.http import Http404
from .models import Rider, OrderAssignment, RiderEarning
from .forms import RiderRegistrationForm, RiderLoginForm
from django.contrib.auth.views import LoginView

@login_required
def rider_dashboard(request):
    try:
        # Get rider profile 
        rider = Rider.objects.get(user=request.user)
        
        # Get orders in a single query
        orders = OrderAssignment.objects.filter(rider=rider).select_related('order')
        
        context = {
            'rider': rider,
            'active_orders': orders.filter(status__in=['ACCEPTED', 'PENDING']),
            'completed_orders': orders.filter(status='DELIVERED'),
            'earnings': RiderEarning.objects.filter(rider=rider).order_by('-date')[:7]
        }
        return render(request, 'dashboard.html', context)
        
    except Rider.DoesNotExist:
        # Redirect to registration if rider profile doesn't exist
        return redirect('rider_registration')
    except Exception as e:
        # Log the error
        print(f"Error accessing dashboard: {str(e)}")
        raise Http404("Dashboard unavailable")

"""def update_availability(request):
    if request.method == 'POST' and request.user.is_authenticated:
        try:
            rider = Rider.objects.get(user=request.user)
            rider.is_available = not rider.is_available
            rider.save()
        except Rider.DoesNotExist:
            pass
    return redirect('rider_dashboard')

def accept_order(request, order_id):
    if request.method == 'POST' and request.user.is_authenticated:
        try:
            assignment = OrderAssignment.objects.get(
                id=order_id,
                rider__user=request.user
            )
            assignment.status = 'ACCEPTED'
            assignment.save()
        except OrderAssignment.DoesNotExist:
            pass
    return redirect('rider_dashboard')

def reject_order(request, order_id):
    if request.method == 'POST' and request.user.is_authenticated:
        try:
            assignment = OrderAssignment.objects.get(
                id=order_id,
                rider__user=request.user
            )
            assignment.status = 'REJECTED'
            assignment.save()
        except OrderAssignment.DoesNotExist:
            pass
    return redirect('rider_dashboard')"""

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
        return reverse('rider_dashboard')