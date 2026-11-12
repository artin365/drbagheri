from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User


class RegisterForm(UserCreationForm):
    first_name = forms.CharField(label="نام", max_length=150)
    last_name = forms.CharField(label="نام خانوادگی", max_length=150)
    email = forms.EmailField(label="ایمیل")

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("first_name", "last_name", "username", "email")

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("این ایمیل قبلاً ثبت شده است.")
        return email


from django.contrib.auth.models import Group  # noqa: E402

from .models import Category, Exam, Question  # noqa: E402


class ExamForm(forms.ModelForm):
    """فرم ساخت/ویرایش آزمون در پنل استاد. گروه فقط با یک سلکت‌باکس انتخاب می‌شود."""
    group = forms.ModelChoiceField(Group.objects.none(), required=False, label="گروه (کلاس)",
                                   empty_label="همهٔ کاربران واردشده",
                                   help_text="فقط اعضای این گروه آزمون را می‌بینند. گروه‌ها را از صفحهٔ «گروه‌ها» بسازید.")

    class Meta:
        model = Exam
        fields = ("title", "description", "duration_minutes", "max_violations", "shuffle_questions", "shuffle_options",
                  "result_mode", "results_release_at", "show_answers", "is_active")
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "results_release_at": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["group"].queryset = Group.objects.order_by("name")
        self.fields["results_release_at"].input_formats = ["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"]
        if self.instance.pk:
            self.fields["group"].initial = self.instance.allowed_groups.first()

    def save(self, commit=True):
        exam = super().save(commit)
        g = self.cleaned_data.get("group")
        exam.allowed_groups.set([g] if g else [])
        return exam


class QuestionForm(forms.ModelForm):
    tags = forms.CharField(label="تگ‌ها", required=False, max_length=400,
                           help_text="با ویرگول یا «،» جدا کنید؛ مثلاً: مثلث، فصل ۳، المپیاد")
    exam = forms.ModelChoiceField(Exam.objects.none(), required=False, label="هم‌زمان به این آزمون هم اضافه شود",
                                  empty_label="— فقط در بانک —")

    class Meta:
        model = Question
        fields = ("text", "option1", "option2", "option3", "option4", "correct", "categories")
        widgets = {"text": forms.Textarea(attrs={"rows": 4}), "categories": forms.CheckboxSelectMultiple}
        labels = {"categories": "دسته‌بندی‌ها"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["exam"].queryset = Exam.objects.order_by("-id")
        if self.instance.pk:
            del self.fields["exam"]
