from django.shortcuts import render, redirect
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django import forms
from django.forms import ModelForm
from django.core.mail import send_mail
from sesame.utils import get_query_string
from .models import CustomUser
from core.utils import add_user_event

class UserRegistrationForm(ModelForm):
    class Meta:
        model = CustomUser
        fields = ['email', 'first_name', 'last_name']

class UserProfileForm(ModelForm):
    class Meta:
        model = CustomUser
        fields = ['email', 'first_name', 'last_name']

def register_view(request):
    if request.method == 'POST':
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.set_unusable_password()  # No password needed for magic link login
            user.save()
            add_user_event(user, 'register', {'ip': request.META.get('REMOTE_ADDR')})
            messages.success(request, 'Registration successful! Check your email for a login link.')

            # Send magic link immediately after registration
            try:
                query_string = get_query_string(user)
                domain = request.get_host()
                protocol = 'https' if request.is_secure() else 'http'
                magic_link = f"{protocol}://{domain}/{query_string}"

                send_mail(
                    subject='Welcome! Your login link',
                    message=f'Welcome to TPS Database!\n\nClick here to log in: {magic_link}\n\nThis link will expire in 1 hour.',
                    from_email=None,
                    recipient_list=[user.email],
                    fail_silently=False,
                )
            except Exception as e:
                messages.warning(request, 'Account created but there was an error sending the login email. Please use the login page.')

            return redirect('login')
    else:
        form = UserRegistrationForm()

    return render(request, 'accounts/register.html', {'form': form})


@login_required
def profile_view(request):
    if request.method == 'POST':
        form = UserProfileForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Profile updated successfully!')
            return redirect('profile')
    else:
        form = UserProfileForm(instance=request.user)
    
    return render(request, 'accounts/profile.html', {'form': form})

def logout_view(request):
    if request.method == 'POST':
        logout(request)
        messages.success(request, 'You have been logged out successfully.')
        return redirect('login')

    return render(request, 'accounts/logout.html')


def magic_link_request(request):
    """Request a magic link to be sent via email"""
    if request.method == 'POST':
        email = request.POST.get('email', '').strip()
        if not email:
            messages.error(request, 'Please enter your email address.')
            return render(request, 'accounts/magic_link_request.html')

        try:
            user = CustomUser.objects.get(email=email)

            # Generate magic link - use home page so sesame middleware can authenticate
            query_string = get_query_string(user)
            domain = request.get_host()
            protocol = 'https' if request.is_secure() else 'http'
            magic_link = f"{protocol}://{domain}/{query_string}"

            # Send email
            send_mail(
                subject='Your login link',
                message=f'Click here to log in: {magic_link}\n\nThis link will expire in 1 hour.',
                from_email=None,  # Uses DEFAULT_FROM_EMAIL
                recipient_list=[user.email],
                fail_silently=False,
            )

            messages.success(request, 'Check your email for a login link!')
            return redirect('login')

        except CustomUser.DoesNotExist:
            # Don't reveal if email exists or not (security)
            messages.success(request, 'If that email is registered, you will receive a login link.')
            return redirect('login')
        except Exception as e:
            messages.error(request, 'There was an error sending the email. Please try again.')
            return render(request, 'accounts/magic_link_request.html')

    return render(request, 'accounts/magic_link_request.html')
