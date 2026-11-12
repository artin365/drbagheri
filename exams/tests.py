from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse

from .models import Attempt, Category, Exam, ExamBankRule, Question, Tag


class PanelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.teacher = User.objects.create_user("teacher", password="x", is_staff=True)
        cls.s1 = User.objects.create_user("s1", password="x", first_name="علی", last_name="رضایی")
        cls.s2 = User.objects.create_user("s2", password="x")

    def setUp(self):
        self.client.force_login(self.teacher)

    def test_default_categories_seeded(self):
        names = set(Category.objects.values_list("name", flat=True))
        self.assertTrue({"سخت", "نهایی", "تیزهوشان", "نهم + آسان", "مدرسه فرهیختگان"} <= names)

    def test_panel_pages_open_and_never_link_to_admin(self):
        g = Group.objects.create(name="نهم الف")
        e = Exam.objects.create(title="E", duration_minutes=5)
        q = Question.objects.create(text="سؤال $x^2$", option1="1", option2="2", correct=1)
        urls = [reverse(n) for n in ("teacher_home", "teacher_exams", "teacher_exam_new", "teacher_groups",
                                     "teacher_students", "teacher_bank", "teacher_question_new")]
        urls += [reverse("teacher_exam_edit", args=[e.pk]), reverse("teacher_group", args=[g.pk]),
                 reverse("teacher_question_edit", args=[q.pk]), reverse("teacher_exam", args=[e.pk])]
        for u in urls:
            r = self.client.get(u)
            self.assertEqual(r.status_code, 200, u)
            self.assertNotIn("/admin/", r.content.decode(), u)

    def test_students_cannot_open_panel(self):
        self.client.force_login(self.s1)
        for n in ("teacher_exams", "teacher_groups", "teacher_bank", "teacher_students"):
            self.assertEqual(self.client.get(reverse(n)).status_code, 302)

    def test_group_create_and_add_members_on_one_page(self):
        r = self.client.post(reverse("teacher_groups"), {"name": "کلاس ۱"})
        g = Group.objects.get(name="کلاس ۱")
        self.assertRedirects(r, reverse("teacher_group", args=[g.pk]))
        self.client.post(reverse("teacher_group", args=[g.pk]), {"action": "members", "u": [self.s1.pk, self.s2.pk, self.teacher.pk]})
        self.assertEqual(set(g.user_set.all()), {self.s1, self.s2})  # استاد عضو نمی‌شود
        self.client.post(reverse("teacher_group", args=[g.pk]), {"action": "members", "u": [self.s1.pk]})
        self.assertEqual(list(g.user_set.all()), [self.s1])

    def test_group_in_use_cannot_be_deleted(self):
        g = Group.objects.create(name="G")
        Exam.objects.create(title="E", duration_minutes=5).allowed_groups.add(g)
        self.client.post(reverse("teacher_group", args=[g.pk]), {"action": "delete"})
        self.assertTrue(Group.objects.filter(pk=g.pk).exists())

    def test_exam_form_picks_group_by_select(self):
        g = Group.objects.create(name="نهم ب")
        page = self.client.get(reverse("teacher_exam_new")).content.decode()
        self.assertIn('<select name="group"', page)
        self.assertIn("نهم ب", page)
        data = {"title": "آزمون ۱", "duration_minutes": 20, "max_violations": 3, "result_mode": "immediate",
                "shuffle_questions": "on", "shuffle_options": "on", "is_active": "on", "group": g.pk}
        r = self.client.post(reverse("teacher_exam_new"), data)
        e = Exam.objects.get(title="آزمون ۱")
        self.assertRedirects(r, reverse("teacher_exam_edit", args=[e.pk]))
        self.assertEqual(list(e.allowed_groups.all()), [g])
        data["group"] = ""
        self.client.post(reverse("teacher_exam_edit", args=[e.pk]), data)
        self.assertEqual(e.allowed_groups.count(), 0)

    def test_scheduled_result_needs_time(self):
        data = {"title": "T", "duration_minutes": 20, "max_violations": 3, "result_mode": "scheduled", "is_active": "on"}
        r = self.client.post(reverse("teacher_exam_new"), data)
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Exam.objects.filter(title="T").exists())
        data["results_release_at"] = "2030-01-02T10:30"
        self.client.post(reverse("teacher_exam_new"), data)
        from django.utils import timezone
        t = timezone.localtime(Exam.objects.get(title="T").results_release_at)
        self.assertEqual((t.hour, t.minute), (10, 30))

    def test_question_with_categories_and_tags(self):
        hard, final = Category.objects.get(name="سخت"), Category.objects.get(name="نهایی")
        r = self.client.post(reverse("teacher_question_new"), {
            "text": "$1+1$ ؟", "option1": "2", "option2": "3", "correct": 1,
            "categories": [hard.pk, final.pk], "tags": "مثلث، #فصل ۳, مثلث"})
        self.assertRedirects(r, reverse("teacher_bank"))
        q = Question.objects.get(text="$1+1$ ؟")
        self.assertIsNone(q.exam_id)
        self.assertEqual({c.name for c in q.categories.all()}, {"سخت", "نهایی"})
        self.assertEqual({t.name for t in q.tags.all()}, {"مثلث", "فصل ۳"})
        page = self.client.get(reverse("teacher_bank")).content.decode()
        self.assertIn("#مثلث", page); self.assertIn("سخت", page)
        self.assertIn("#مثلث", self.client.get(reverse("teacher_bank"), {"cat": hard.pk}).content.decode())
        self.assertNotIn("#مثلث", self.client.get(reverse("teacher_bank"), {"cat": Category.objects.get(name="تیزهوشان").pk}).content.decode())
        self.assertIn("#مثلث", self.client.get(reverse("teacher_bank"), {"tag": Tag.objects.get(name="مثلث").pk}).content.decode())

    def test_invalid_correct_option_rejected(self):
        r = self.client.post(reverse("teacher_question_new"), {"text": "x", "option1": "a", "option2": "b", "correct": 3})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Question.objects.filter(text="x").exists())

    def test_bulk_actions_and_import_to_exam(self):
        e = Exam.objects.create(title="E", duration_minutes=5)
        qs = [Question.objects.create(text=f"q{i}", option1="a", option2="b") for i in range(3)]
        cat = Category.objects.get(name="نهایی")
        ids = [q.pk for q in qs[:2]]
        self.client.post(reverse("teacher_bank"), {"q": ids, "action": "cat_add", "category": cat.pk})
        self.assertEqual(cat.questions.count(), 2)
        self.client.post(reverse("teacher_bank"), {"q": ids, "action": "tag_add", "tags": "الف، ب"})
        self.assertEqual(qs[0].tags.count(), 2)
        self.client.post(reverse("teacher_bank"), {"q": ids, "action": "import", "exam": e.pk})
        self.client.post(reverse("teacher_bank"), {"q": ids, "action": "import", "exam": e.pk})  # تکراری اضافه نمی‌شود
        self.assertEqual(e.questions.count(), 2)
        self.client.post(reverse("teacher_bank"), {"q": ids[:1], "action": "cat_remove", "category": cat.pk})
        self.assertEqual(cat.questions.count(), 1)

    def test_random_rule_by_category_and_no_duplicates(self):
        from .views import pick_questions
        e = Exam.objects.create(title="E", duration_minutes=5)
        cat = Category.objects.get(name="سخت")
        for i in range(4):
            Question.objects.create(text=f"b{i}", option1="a", option2="b").categories.add(cat)
        self.client.post(reverse("teacher_rule_add", args=[e.pk]), {"category": cat.pk, "count": 3})
        self.client.post(reverse("teacher_rule_add", args=[e.pk]), {"category": cat.pk, "count": 1})  # تکراری
        self.client.post(reverse("teacher_rule_add", args=[e.pk]), {"category": Category.objects.get(name="نهایی").pk, "count": 1})  # خالی
        self.assertEqual(ExamBankRule.objects.filter(exam=e).count(), 1)
        first = Question.objects.filter(exam__isnull=True).first()
        self.client.post(reverse("teacher_bank"), {"q": [first.pk], "action": "import", "exam": e.pk})
        for _ in range(10):
            got = pick_questions(e)
            self.assertEqual(len(got), 4)  # 1 ثابت + 3 تصادفی
            texts = [q.text for q in got]
            self.assertEqual(len(set(texts)), 4)

    def test_exam_with_attempts_cannot_be_deleted(self):
        e = Exam.objects.create(title="E", duration_minutes=5)
        from django.utils import timezone
        Attempt.objects.create(user=self.s1, exam=e, deadline=timezone.now())
        self.client.post(reverse("teacher_exam_delete", args=[e.pk]))
        self.assertTrue(Exam.objects.filter(pk=e.pk).exists())
        e2 = Exam.objects.create(title="E2", duration_minutes=5)
        self.client.post(reverse("teacher_exam_delete", args=[e2.pk]))
        self.assertFalse(Exam.objects.filter(pk=e2.pk).exists())

    def test_category_delete_blocked_when_used_by_rule(self):
        e = Exam.objects.create(title="E", duration_minutes=5)
        cat = Category.objects.create(name="X")
        ExamBankRule.objects.create(exam=e, category=cat, count=1)
        self.client.post(reverse("teacher_categories"), {"action": "delete", "id": cat.pk})
        self.assertTrue(Category.objects.filter(pk=cat.pk).exists())
        self.client.post(reverse("teacher_categories"), {"action": "add", "name": "جدید"})
        self.assertTrue(Category.objects.filter(name="جدید").exists())

    def test_group_restricts_students(self):
        g = Group.objects.create(name="G"); g.user_set.add(self.s1)
        e = Exam.objects.create(title="E", duration_minutes=5); e.allowed_groups.add(g)
        self.client.force_login(self.s1); self.assertContains(self.client.get("/"), "E")
        self.client.force_login(self.s2); self.assertNotContains(self.client.get("/"), "<h3>E</h3>")
