from django.conf import settings
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone


DEFAULT_CATEGORIES = ("سخت", "نهایی", "تیزهوشان", "نهم + آسان", "مدرسه فرهیختگان")


class Category(models.Model):
    """دسته‌بندی سؤال‌ها (مثلاً «سخت»، «نهایی»). هر سؤال می‌تواند چند دسته‌بندی داشته باشد."""
    name = models.CharField("نام دسته‌بندی", max_length=80, unique=True)
    order = models.PositiveSmallIntegerField("ترتیب", default=0)

    class Meta:
        ordering = ["order", "id"]
        verbose_name, verbose_name_plural = "دسته‌بندی", "دسته‌بندی‌ها"

    def __str__(self):
        return self.name

    @property
    def hue(self):  # رنگ ثابت برای هر دسته‌بندی در نمایش
        return (self.pk or 0) * 67 % 360


class Tag(models.Model):
    name = models.CharField("تگ", max_length=60, unique=True)

    class Meta:
        ordering = ["name"]
        verbose_name, verbose_name_plural = "تگ", "تگ‌ها"

    def __str__(self):
        return self.name


class Exam(models.Model):
    class ResultMode(models.TextChoices):
        IMMEDIATE = "immediate", "بلافاصله پس از پایان آزمون"
        SCHEDULED = "scheduled", "در زمان مشخص‌شده توسط استاد"

    title = models.CharField("عنوان", max_length=200)
    description = models.TextField("توضیحات", blank=True)
    duration_minutes = models.PositiveSmallIntegerField("مدت (دقیقه)", validators=[MinValueValidator(1)])
    max_violations = models.PositiveSmallIntegerField("حداکثر تخلف مجاز", default=3, validators=[MinValueValidator(1)])
    shuffle_questions = models.BooleanField("ترتیب سؤال‌ها تصادفی باشد", default=True)
    shuffle_options = models.BooleanField("ترتیب گزینه‌ها تصادفی باشد", default=True)
    result_mode = models.CharField("زمان اعلام نتیجه", max_length=12, choices=ResultMode.choices, default=ResultMode.IMMEDIATE)
    results_release_at = models.DateTimeField("زمان اعلام نتیجه", null=True, blank=True,
                                              help_text="فقط وقتی «در زمان مشخص» انتخاب شده لازم است.")
    show_answers = models.BooleanField("همراه نتیجه، پاسخ صحیح و مرور سؤال‌ها نشان داده شود", default=False)
    allowed_groups = models.ManyToManyField(Group, blank=True, verbose_name="گروه‌های مجاز",
        help_text="خالی = همهٔ کاربران واردشده. در غیر این صورت فقط اعضای این گروه‌ها (مثلاً یک کلاس) دسترسی دارند.")
    is_active = models.BooleanField("فعال", default=True)

    def __str__(self):
        return self.title

    def clean(self):
        if self.result_mode == self.ResultMode.SCHEDULED and not self.results_release_at:
            raise ValidationError({"results_release_at": "برای اعلام زمان‌دار، زمان اعلام نتیجه را مشخص کنید."})

    def total_questions(self):
        return self.questions.count() + sum(r.count for r in self.bank_rules.all())

    def results_open(self):
        return self.result_mode == self.ResultMode.IMMEDIATE or bool(
            self.results_release_at and timezone.now() >= self.results_release_at)


class Question(models.Model):
    """سؤال یا متعلق به یک آزمون است (exam پر است) یا سؤال بانک است (exam خالی)."""
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name="questions", null=True, blank=True)
    categories = models.ManyToManyField(Category, blank=True, related_name="questions", verbose_name="دسته‌بندی‌ها")
    tags = models.ManyToManyField(Tag, blank=True, related_name="questions", verbose_name="تگ‌ها")
    order = models.PositiveIntegerField("ترتیب", default=0)
    text = models.TextField("متن سؤال (فرمول با $...$)")
    option1 = models.CharField("گزینهٔ ۱", max_length=300)
    option2 = models.CharField("گزینهٔ ۲", max_length=300)
    option3 = models.CharField("گزینهٔ ۳", max_length=300, blank=True)
    option4 = models.CharField("گزینهٔ ۴", max_length=300, blank=True)
    correct = models.PositiveSmallIntegerField("گزینهٔ صحیح", choices=[(i, f"گزینهٔ {i}") for i in range(1, 5)], default=1)
    origin = models.ForeignKey("self", null=True, blank=True, editable=False, on_delete=models.SET_NULL, related_name="copies")

    class Meta:
        ordering = ["order", "id"]
        constraints = [
            models.CheckConstraint(condition=Q(correct__gte=1) & Q(correct__lte=4), name="correct_1_to_4"),
        ]

    def clean(self):
        opts = [self.option1, self.option2, self.option3, self.option4]
        if self.correct in (1, 2, 3, 4) and not (opts[self.correct - 1] or "").strip():
            raise ValidationError("گزینهٔ صحیح باید یکی از گزینه‌های پرشده باشد.")
        if self.option4 and not self.option3:
            raise ValidationError("گزینهٔ ۳ را پر کنید یا گزینهٔ ۴ را خالی بگذارید.")

    def __str__(self):
        return self.text[:60]


CONTENT = ("text", "option1", "option2", "option3", "option4", "correct")


@receiver(post_save, sender=Question)
def mirror_to_bank(sender, instance, raw=False, **kwargs):
    """هر سؤالی که مستقیم در یک آزمون ساخته شود (مثلاً از ادمین)، یک نسخه در بانک سؤال هم می‌گیرد."""
    if raw or not instance.exam_id:
        return
    data = {f: getattr(instance, f) for f in CONTENT}
    b = instance.origin
    if b is None:
        b = Question.objects.create(origin=instance, **data)
        Question.objects.filter(pk=instance.pk).update(origin=b)
    elif b.origin_id == instance.pk:  # فقط نسخهٔ آینه‌ای همگام می‌شود، نه سؤال‌های واردشده از بانک
        Question.objects.filter(pk=b.pk).update(**data)


class ExamBankRule(models.Model):
    """«از این دسته‌بندی، N سؤال تصادفی برای هر دانش‌آموز بیاور.» (دسته‌بندی خالی = کل بانک)"""
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name="bank_rules")
    category = models.ForeignKey(Category, on_delete=models.PROTECT, null=True, blank=True, verbose_name="دسته‌بندی")
    count = models.PositiveSmallIntegerField("تعداد سؤال تصادفی", validators=[MinValueValidator(1)], default=1)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["exam", "category"], name="one_rule_per_exam_category")]

    def pool(self):
        qs = Question.objects.filter(exam__isnull=True)
        return qs.filter(categories=self.category) if self.category_id else qs

    def clean(self):
        n = self.pool().count()
        if self.count and self.count > n:
            raise ValidationError(f"این دسته‌بندی فقط {n} سؤال دارد.")


class Attempt(models.Model):
    class Status(models.TextChoices):
        IN_PROGRESS = "in_progress", "در حال برگزاری"
        SUBMITTED = "submitted", "ثبت‌شده"
        DISQUALIFIED = "disqualified", "ابطال‌شده به‌دلیل تخلف"
        EXPIRED = "expired", "پایان زمان"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="attempts")
    exam = models.ForeignKey(Exam, on_delete=models.PROTECT, related_name="attempts")
    questions = models.ManyToManyField(Question, blank=True)  # مجموعهٔ سؤال‌های همین نفر (ثابت‌شده هنگام شروع)
    started_at = models.DateTimeField(auto_now_add=True)
    deadline = models.DateTimeField()
    finished_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.IN_PROGRESS)
    score = models.FloatField(null=True, blank=True)
    total = models.PositiveSmallIntegerField(default=0)
    answered = models.PositiveSmallIntegerField(default=0)
    correct = models.PositiveSmallIntegerField(default=0)
    violations = models.PositiveSmallIntegerField(default=0)

    class Meta:
        constraints = [
            # شرکت یک‌بار: ضمانت در سطح دیتابیس، حتی در درخواست‌های هم‌زمان
            models.UniqueConstraint(fields=["user", "exam"], name="one_attempt_per_user_exam"),
            models.CheckConstraint(condition=Q(score__isnull=True) | (Q(score__gte=0) & Q(score__lte=100)),
                                   name="score_in_0_100"),
        ]


class Answer(models.Model):
    attempt = models.ForeignKey(Attempt, on_delete=models.CASCADE, related_name="answers")
    question = models.ForeignKey(Question, on_delete=models.PROTECT)
    selected = models.PositiveSmallIntegerField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=["attempt", "question"], name="one_answer_per_question"),
                       models.CheckConstraint(condition=Q(selected__gte=1) & Q(selected__lte=4), name="selected_1_to_4")]


class Violation(models.Model):
    class Kind(models.TextChoices):
        TAB_HIDDEN = "tab_hidden", "تغییر تب یا مینیمایز"
        WINDOW_BLUR = "window_blur", "خروج از پنجرهٔ آزمون"
        COPY_PASTE = "copy_paste", "تلاش برای کپی یا چسباندن"
        RESUME = "resume", "بارگذاری مجدد صفحه (بدون جریمه)"

    attempt = models.ForeignKey(Attempt, on_delete=models.CASCADE, related_name="violation_log")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    counted = models.BooleanField(default=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
