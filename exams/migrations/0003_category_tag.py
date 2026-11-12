import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("exams", "0002_origin")]

    operations = [
        migrations.CreateModel(
            name="Category",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=80, unique=True, verbose_name="نام دسته‌بندی")),
                ("order", models.PositiveSmallIntegerField(default=0, verbose_name="ترتیب")),
            ],
            options={"verbose_name": "دسته‌بندی", "verbose_name_plural": "دسته‌بندی‌ها", "ordering": ["order", "id"]},
        ),
        migrations.CreateModel(
            name="Tag",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=60, unique=True, verbose_name="تگ")),
            ],
            options={"verbose_name": "تگ", "verbose_name_plural": "تگ‌ها", "ordering": ["name"]},
        ),
        migrations.AddField(
            model_name="question", name="categories",
            field=models.ManyToManyField(blank=True, related_name="questions", to="exams.category", verbose_name="دسته‌بندی‌ها"),
        ),
        migrations.AddField(
            model_name="question", name="tags",
            field=models.ManyToManyField(blank=True, related_name="questions", to="exams.tag", verbose_name="تگ‌ها"),
        ),
        migrations.AddField(
            model_name="exambankrule", name="category",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                                    to="exams.category", verbose_name="دسته‌بندی"),
        ),
    ]
