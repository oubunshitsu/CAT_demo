from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm


class EmailUserCreationForm(UserCreationForm):
    email = forms.EmailField(required=False)

    class Meta(UserCreationForm.Meta):
        model = get_user_model()
        fields = ("username", "email")

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = (self.cleaned_data.get("email") or "").strip()
        if commit:
            user.save()
        return user


class UsernameResetRequestForm(forms.Form):
    username = forms.CharField(max_length=150)

    def clean_username(self):
        return self.cleaned_data["username"].strip()
