from django.shortcuts import render, redirect
from .forms import merchantRegistrationForm, addRestaurantForm
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login
from django.contrib.auth.forms import AuthenticationForm
from .models import MerchantProfile, InventoryItem, Order, Payment
from .forms import MerchantStatusForm, InventoryItemForm

def merchantRegistration(request):
    if request.method == 'POST':
        form = merchantRegistrationForm(request.POST)
        if form.is_valid():
            # Optional: Add password match check
            if form.cleaned_data['password'] == form.cleaned_data['retypePassword']:
                form.save()
                return redirect('merchant_register_success')  
            else:
                form.add_error('retypePassword', 'Passwords do not match')
    else:
        form = merchantRegistrationForm()
    return render(request, 'merchantRegister.html', {'form': form} )


def merchant_register_success(request):
    return render(request, 'merchant_register_success.html')

def merchant_login(request):
    if request.method == 'POST':
        form = AuthenticationForm(data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(request, username=username, password=password)
            if user is not None:
                login(request, user)
                return redirect('add-restaurant')
    else:
        form = AuthenticationForm()
    return render(request, 'merchantLogin.html', {'form': form})

@login_required
def addRestaurant(request):
    if request.method == 'POST':
        form = addRestaurantForm(request.POST, request.FILES)
        if form.is_valid():
            restaurant = form.save(commit=False)
            restaurant.is_approved = False  
            restaurant.save()
            return redirect('home')  
    else:
        form = addRestaurantForm()
    return render(request, 'addRestaurant.html', {'form': form})


@login_required
def dashboard_home(request):
    merchant = MerchantProfile.objects.get(user=request.user)
    status_form = MerchantStatusForm(instance=merchant)

    if request.method == 'POST':
        status_form = MerchantStatusForm(request.POST, instance=merchant)
        if status_form.is_valid():
            status_form.save()
            return redirect('dashboard_home')

    context = {
        'merchant': merchant,
        'status_form': status_form,
    }
    return render(request, 'dashboard_home.html', context)


@login_required
def inventory_management(request):
    merchant = MerchantProfile.objects.get(user=request.user)
    items = InventoryItem.objects.filter(merchant=merchant)

    if request.method == 'POST':
        form = InventoryItemForm(request.POST)
        if form.is_valid():
            item = form.save(commit=False)
            item.merchant = merchant
            item.save()
            return redirect('inventory_management')
    else:
        form = InventoryItemForm()

    return render(request, 'inventory.html', {'items': items, 'form': form})


@login_required
def order_list(request):
    merchant = MerchantProfile.objects.get(user=request.user)
    orders = Order.objects.filter(merchant=merchant).order_by('-date')
    return render(request, 'orders.html', {'orders': orders})


@login_required
def payment_list(request):
    merchant = MerchantProfile.objects.get(user=request.user)
    payments = Payment.objects.filter(merchant=merchant).order_by('-transaction_date')
    return render(request, 'payments.html', {'payments': payments})
