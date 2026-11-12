from django.db import migrations

AUTO = "همهٔ سؤال‌ها (خودکار)"
DEFAULTS = ("سخت", "نهایی", "تیزهوشان", "نهم + آسان", "مدرسه فرهیختگان")


def forward(apps, schema_editor):
    """دسته‌بندی‌های پیش‌فرض ساخته می‌شود و هر «بانک» قدیمی به یک «دسته‌بندی» با همان نام تبدیل می‌شود."""
    Bank, Cat = apps.get_model("exams", "QuestionBank"), apps.get_model("exams", "Category")
    Question, Rule = apps.get_model("exams", "Question"), apps.get_model("exams", "ExamBankRule")
    for i, name in enumerate(DEFAULTS, 1):
        Cat.objects.get_or_create(name=name, defaults={"order": i})
    for bank in Bank.objects.all():
        if bank.name == AUTO:
            continue  # بانک خودکار = کل بانک، دسته‌بندی نمی‌خواهد
        cat, _ = Cat.objects.get_or_create(name=bank.name[:80], defaults={"order": 100 + bank.pk})
        for q in Question.objects.filter(bank=bank):
            q.categories.add(cat)
        Rule.objects.filter(bank=bank).update(category=cat)


class Migration(migrations.Migration):
    dependencies = [("exams", "0003_category_tag")]
    operations = [migrations.RunPython(forward, migrations.RunPython.noop)]
