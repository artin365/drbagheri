from django.contrib.auth import views as auth
from django.urls import path
from . import teacher as t
from . import views as v

urlpatterns = [
    path("", v.home, name="home"),
    path("register/", v.register, name="register"),
    path("login/", auth.LoginView.as_view(template_name="auth_form.html",
         extra_context={"title": "ورود", "btn": "ورود"}), name="login"),
    path("logout/", auth.LogoutView.as_view(), name="logout"),
    path("exam/<int:exam_id>/start/", v.start, name="start"),
    path("attempt/<int:attempt_id>/", v.take, name="take"),
    path("attempt/<int:attempt_id>/answer/", v.api_answer, name="answer"),
    path("attempt/<int:attempt_id>/violation/", v.api_violation, name="violation"),
    path("attempt/<int:attempt_id>/submit/", v.api_submit, name="submit"),
    path("attempt/<int:attempt_id>/result/", v.result, name="result"),
    path("teacher/", t.teacher_home, name="teacher_home"),
    path("teacher/exam/<int:exam_id>/", t.teacher_exam, name="teacher_exam"),
    path("teacher/exam/<int:exam_id>/xlsx/", t.teacher_xlsx, name="teacher_xlsx"),
    path("teacher/xlsx/", t.teacher_xlsx_all, name="teacher_xlsx_all"),
    path("teacher/exams/", t.teacher_exams, name="teacher_exams"),
    path("teacher/exams/new/", t.teacher_exam_form, name="teacher_exam_new"),
    path("teacher/exams/<int:exam_id>/edit/", t.teacher_exam_form, name="teacher_exam_edit"),
    path("teacher/exams/<int:exam_id>/delete/", t.teacher_exam_delete, name="teacher_exam_delete"),
    path("teacher/exams/<int:exam_id>/questions/<int:question_id>/remove/", t.teacher_exam_qremove, name="teacher_exam_qremove"),
    path("teacher/exams/<int:exam_id>/rules/add/", t.teacher_rule_add, name="teacher_rule_add"),
    path("teacher/exams/<int:exam_id>/rules/<int:rule_id>/delete/", t.teacher_rule_delete, name="teacher_rule_delete"),
    path("teacher/groups/", t.teacher_groups, name="teacher_groups"),
    path("teacher/groups/<int:group_id>/", t.teacher_group, name="teacher_group"),
    path("teacher/students/", t.teacher_students, name="teacher_students"),
    path("teacher/bank/", t.teacher_bank, name="teacher_bank"),
    path("teacher/bank/new/", t.teacher_question_form, name="teacher_question_new"),
    path("teacher/bank/<int:question_id>/edit/", t.teacher_question_form, name="teacher_question_edit"),
    path("teacher/bank/categories/", t.teacher_categories, name="teacher_categories"),
    path("teacher/attempt/<int:attempt_id>/", t.teacher_attempt, name="teacher_attempt"),
]
