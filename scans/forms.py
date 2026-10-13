"""
Forms for scans app.
"""

from django import forms


class NewScanForm(forms.Form):
    """Form for uploading a new eye scan."""

    image = forms.ImageField(
        label="Rasm",
        error_messages={
            "required": "Iltimos, rasm yuklang.",
            "invalid_image": "Yuklangan fayl rasm emas yoki buzilgan.",
        },
    )
    child_name = forms.CharField(
        label="Bolaning ismi",
        max_length=120,
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "Masalan: Aziz"}),
    )
    child_age = forms.IntegerField(
        label="Yoshi",
        required=False,
        min_value=3,
        max_value=17,
        widget=forms.NumberInput(attrs={"placeholder": "3–17"}),
        error_messages={
            "min_value": "Yosh 3 dan kam bo'lmasligi kerak.",
            "max_value": "Yosh 17 dan oshmasligi kerak.",
        },
    )
    notes = forms.CharField(
        label="Izoh",
        required=False,
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": "Qo'shimcha ma'lumot..."}),
    )

    def clean_image(self):
        image = self.cleaned_data.get("image")
        if image:
            allowed_types = {"image/jpeg", "image/png", "image/webp"}
            if image.content_type not in allowed_types:
                raise forms.ValidationError(
                    "Faqat JPG, PNG yoki WEBP formatdagi rasmlar qabul qilinadi."
                )
            if image.size > 8 * 1024 * 1024:
                raise forms.ValidationError("Rasm hajmi 8 MB dan oshmasligi kerak.")
        return image
