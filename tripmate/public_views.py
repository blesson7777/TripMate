from django import forms
from django.conf import settings
from django.shortcuts import render

from users.models import AccountDeletionRequest, User


class AccountDeletionRequestForm(forms.Form):
    email = forms.EmailField(
        label="Account email",
        widget=forms.EmailInput(
            attrs={
                "placeholder": "name@example.com",
                "autocomplete": "email",
            }
        ),
    )
    role = forms.ChoiceField(
        label="Account type",
        choices=[
            (User.Role.DRIVER, "Driver"),
            (User.Role.TRANSPORTER, "Transporter"),
        ],
    )
    note = forms.CharField(
        label="Reason or notes",
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 4,
                "placeholder": "Optional details to help us identify your account.",
            }
        ),
    )


def _support_email() -> str:
    email = (settings.DEFAULT_FROM_EMAIL or "").strip()
    return email or "support@tripmate.local"


def privacy_policy(request):
    return render(
        request,
        "public/privacy_policy.html",
        {
            "support_email": _support_email(),
        },
    )


def account_deletion(request):
    submitted = False
    if request.method == "POST":
        form = AccountDeletionRequestForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data["email"].strip().lower()
            role = form.cleaned_data["role"]
            note = form.cleaned_data["note"].strip()
            linked_user = User.objects.filter(email__iexact=email, role=role).first()
            existing = (
                AccountDeletionRequest.objects.filter(
                    email__iexact=email,
                    role=role,
                    status=AccountDeletionRequest.Status.REQUESTED,
                )
                .order_by("-requested_at")
                .first()
            )
            if existing is None:
                AccountDeletionRequest.objects.create(
                    email=email,
                    role=role,
                    user=linked_user,
                    source=AccountDeletionRequest.Source.WEB,
                    note=note,
                )
            submitted = True
            form = AccountDeletionRequestForm(
                initial={"email": email, "role": role, "note": note}
            )
    else:
        form = AccountDeletionRequestForm()

    return render(
        request,
        "public/account_deletion.html",
        {
            "form": form,
            "submitted": submitted,
            "support_email": _support_email(),
        },
    )
