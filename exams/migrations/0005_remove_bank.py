from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("exams", "0004_banks_to_categories")]

    operations = [
        migrations.RemoveConstraint(model_name="question", name="exam_xor_bank"),
        migrations.RemoveConstraint(model_name="exambankrule", name="one_rule_per_exam_bank"),
        migrations.RemoveField(model_name="exambankrule", name="bank"),
        migrations.RemoveField(model_name="question", name="bank"),
        migrations.DeleteModel(name="QuestionBank"),
        migrations.AddConstraint(
            model_name="exambankrule",
            constraint=models.UniqueConstraint(fields=("exam", "category"), name="one_rule_per_exam_category"),
        ),
    ]
