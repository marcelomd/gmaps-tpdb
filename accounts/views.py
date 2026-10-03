import logging
from django.conf import settings
from django.shortcuts import render, redirect
from django.core.cache import cache
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.forms import ModelForm
from django.core.mail import send_mail
from sesame.utils import get_query_string
from honeypot.decorators import check_honeypot
from .models import CustomUser
from core.utils import add_user_event, client_ip

logger = logging.getLogger(__name__)

MAGIC_LINK_COOLDOWN_SECONDS = 60
REGISTERED_MESSAGE = 'Registration successful! Check your email for a login link.'
UNKNOWN_OR_SENT_MESSAGE = 'If that email is registered, you will receive a login link.'


class UserForm(ModelForm):
    class Meta:
        model = CustomUser
        fields = ['email', 'first_name', 'last_name']


def send_login_link(request, user, subject, intro=''):
    # Points at the home page: the sesame middleware authenticates any URL carrying the token
    if settings.SITE_URL:
        base_url = settings.SITE_URL
    else:
        protocol = 'https' if request.is_secure() else 'http'
        base_url = f"{protocol}://{request.get_host()}"
    magic_link = f"{base_url}/{get_query_string(user)}"

    send_mail(
        subject=subject,
        message=f'{intro}Click here to log in: {magic_link}\n\nThis link will expire in 1 hour.',
        from_email=None,  # Uses DEFAULT_FROM_EMAIL
        recipient_list=[user.email],
        fail_silently=False,
    )


def cooldown_elapsed(email):
    """True at most once per MAGIC_LINK_COOLDOWN_SECONDS for an email"""
    return cache.add(f'magic-link:{email.lower()}', 1, MAGIC_LINK_COOLDOWN_SECONDS)


@check_honeypot
def register_view(request):
    if request.method == 'POST':
        email = request.POST.get('email', '').strip()
        existing = CustomUser.objects.filter(email__iexact=email).first() if email else None
        if existing:
            # Same outcome as a new registration so the form can't be used to probe which emails are registered
            if cooldown_elapsed(email):
                try:
                    send_login_link(request, existing, 'Your login link')
                except Exception:
                    logger.exception('Failed to send magic link')
            messages.success(request, REGISTERED_MESSAGE)
            return redirect('login')

        form = UserForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.set_unusable_password()  # Login is by magic link only
            user.save()
            add_user_event(user, 'register', {'ip': client_ip(request)})
            messages.success(request, REGISTERED_MESSAGE)

            try:
                send_login_link(request, user, 'Welcome! Your login link', 'Welcome to TPS Database!\n\n')
            except Exception:
                logger.exception('Failed to send welcome email')
                messages.warning(request, 'Account created but there was an error sending the login email. Please use the login page.')

            return redirect('login')
    else:
        form = UserForm()

    return render(request, 'accounts/register.html', {'form': form})


@login_required
def profile_view(request):
    if request.method == 'POST':
        form = UserForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Profile updated successfully!')
            return redirect('profile')
    else:
        form = UserForm(instance=request.user)

    return render(request, 'accounts/profile.html', {'form': form})


def logout_view(request):
    if request.method == 'POST':
        logout(request)
        messages.success(request, 'You have been logged out successfully.')
        return redirect('login')

    return render(request, 'accounts/logout.html')


@check_honeypot
def magic_link_request(request):
    if request.method == 'POST':
        email = request.POST.get('email', '').strip()
        if not email:
            messages.error(request, 'Please enter your email address.')
            return render(request, 'accounts/magic_link_request.html')

        # Every outcome below shows the same message so the form can't be used to probe which emails are registered.
        # The throttle runs before the lookup for the same reason.
        if not cooldown_elapsed(email):
            messages.success(request, UNKNOWN_OR_SENT_MESSAGE)
            return redirect('login')

        try:
            user = CustomUser.objects.get(email=email)
            send_login_link(request, user, 'Your login link')
        except CustomUser.DoesNotExist:
            pass
        except Exception:
            logger.exception('Failed to send magic link')

        messages.success(request, UNKNOWN_OR_SENT_MESSAGE)
        return redirect('login')

    return render(request, 'accounts/magic_link_request.html')
