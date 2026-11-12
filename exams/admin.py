from django import forms
from django.contrib import admin
from django.contrib.admin.widgets import FilteredSelectMultiple
from django.contrib.auth.admin import GroupAdmin as BaseGroupAdmin
from django.contrib.auth.models import Group, User

from .models import Attempt, Category, Exam, ExamBankRule, Question, Tag, Violation


class QuestionInline(admin.StackedInline):
    model = Question
    extra = 3
    fields = ("order", "text", ("option1", "option2"), ("option3", "option4"), "correct")


class BankRuleInline(admin.TabularInline):
    model = ExamBankRule
    extra = 1
    verbose_name, verbose_name_plural = "سؤال تصادفی از دسته‌بندی", "سؤال‌های تصادفی از دسته‌بندی‌ها (برای هر دانش‌آموز متفاوت)"


@admin.register(Exam)
class ExamAdmin(admin.ModelAdmin):
    list_display = ("title", "duration_minutes", "is_active", "result_mode", "shuffle_questions", "shuffle_options")
    filter_horizontal = ("allowed_groups",)
    fieldsets = [(None, {"fields": ("title", "description", "duration_minutes", "max_violations")}),
                 ("دسترسی", {"fields": ("allowed_groups", "is_active")}),
                 ("تصادفی‌سازی", {"fields": ("shuffle_questions", "shuffle_options")}),
                 ("اعلام نتیجه", {"fields": ("result_mode", "results_release_at", "show_answers")})]
    inlines = [QuestionInline, BankRuleInline]


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "order")
    list_editable = ("order",)


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    search_fields = ("name",)


class GroupForm(forms.ModelForm):
    users = forms.ModelMultipleChoiceField(User.objects.all(), required=False, label="اعضا",
                                           widget=FilteredSelectMultiple("کاربران", False))

    class Meta:
        model = Group
        fields = ("name",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["users"].initial = self.instance.user_set.all()


admin.site.unregister(Group)


@admin.register(Group)
class GroupAdmin(BaseGroupAdmin):  # ساخت کلاس و افزودن دانش‌آموزان در یک صفحه
    form = GroupForm
    fields = ("name", "users")
    filter_horizontal = ()

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        form.instance.user_set.set(form.cleaned_data["users"])


class ReadOnly(admin.ModelAdmin):
    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False  # سابقه دائمی است


@admin.register(Attempt)
class AttemptAdmin(ReadOnly):
    list_display = ("user", "exam", "status", "score", "correct", "total", "violations", "started_at", "finished_at")
    list_filter = ("exam", "status")


@admin.register(Violation)
class ViolationAdmin(ReadOnly):
    list_display = ("attempt", "kind", "counted", "ip", "created_at")
    list_filter = ("kind",)
