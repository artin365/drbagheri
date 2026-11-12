import json
import random
from datetime import timedelta

from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.db.models import F, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import RegisterForm
from .models import Answer, Attempt, Exam, Violation

GRACE = timedelta(seconds=3)  # تحمل تأخیر شبکه؛ زمان فقط با ساعت سرور سنجیده می‌شود
S = Attempt.Status


def visible_exams(user):
    """آزمون‌های فعالی که این کاربر اجازهٔ دیدن و شرکت دارد (گروه‌های مجاز)."""
    qs = Exam.objects.filter(is_active=True)
    if user.is_superuser:
        return qs
    cond = Q(allowed_groups__isnull=True)
    if user.is_authenticated:
        cond |= Q(allowed_groups__in=user.groups.all())
    return qs.filter(cond).distinct()


def home(request):
    exams = list(visible_exams(request.user))
    if request.user.is_authenticated:
        mine = {a.exam_id: a for a in Attempt.objects.filter(user=request.user)}
        for e in exams:
            e.attempt = mine.get(e.id)
    return render(request, "home.html", {"exams": exams})


def register(request):
    form = RegisterForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        login(request, form.save())
        return redirect("home")
    return render(request, "auth_form.html", {"form": form, "title": "ساخت حساب", "btn": "ثبت‌نام"})


def pick_questions(exam):
    """سؤال‌های ثابت آزمون + N سؤال تصادفی از هر دسته‌بندی تعریف‌شده (بدون تکرار)."""
    picked = list(exam.questions.all())
    seen = {q.pk for q in picked} | {q.origin_id for q in picked if q.origin_id}
    for r in exam.bank_rules.select_related("category"):
        pool = [q for q in r.pool() if q.pk not in seen and q.origin_id not in seen]
        for q in random.sample(pool, min(r.count, len(pool))):
            picked.append(q)
            seen.add(q.pk)
    return picked


def finalize(a, status):
    """نمره را فقط سرور و از روی پاسخ‌های ذخیره‌شده حساب می‌کند. داخل تراکنش و روی ردیف قفل‌شده صدا زده شود."""
    a.total = a.questions.count()
    a.answered = a.answers.count()
    a.correct = a.answers.filter(selected=F("question__correct")).count()
    a.score = round(100 * a.correct / a.total, 1) if a.total else 0
    a.status, a.finished_at = status, timezone.now()
    a.save()


def locked(request, attempt_id):
    a = get_object_or_404(Attempt.objects.select_for_update().select_related("exam"),
                          pk=attempt_id, user=request.user)  # فقط صاحب تلاش
    if a.status == S.IN_PROGRESS and timezone.now() > a.deadline + GRACE:
        finalize(a, S.EXPIRED)
    return a


def body(request):
    try:
        return json.loads(request.body or b"{}")
    except ValueError:
        return {}


@login_required
@require_POST
def start(request, exam_id):
    exam = get_object_or_404(visible_exams(request.user), pk=exam_id)
    picked = pick_questions(exam)
    if not picked:
        return redirect("home")
    try:
        with transaction.atomic():
            a = Attempt.objects.create(user=request.user, exam=exam,
                                       deadline=timezone.now() + timedelta(minutes=exam.duration_minutes))
            a.questions.set(picked)
    except IntegrityError:  # قبلاً شرکت کرده یا هم‌زمان دوبار کلیک شده
        a = Attempt.objects.get(user=request.user, exam=exam)
    return redirect("take", a.pk)


@login_required
def take(request, attempt_id):
    with transaction.atomic():
        a = locked(request, attempt_id)
        if a.status != S.IN_PROGRESS:
            return redirect("result", a.pk)
        now = timezone.now()
        if now - a.started_at > timedelta(seconds=10):  # بارگذاری مجدد ثبت می‌شود
            Violation.objects.create(attempt=a, kind="resume", counted=False, ip=request.META.get("REMOTE_ADDR"),
                                     user_agent=request.META.get("HTTP_USER_AGENT", "")[:300])
    rng = random.Random(a.pk)  # ترتیب سؤال و گزینه برای هر نفر متفاوت ولی ثابت
    questions = list(a.questions.all())
    if a.exam.shuffle_questions:
        rng.shuffle(questions)
    for q in questions:
        q.opts = [(n, t) for n, t in enumerate([q.option1, q.option2, q.option3, q.option4], 1) if t]
        if a.exam.shuffle_options:
            rng.shuffle(q.opts)
    return render(request, "take.html", {
        "a": a, "questions": questions, "seconds_left": max(0, int((a.deadline - now).total_seconds())),
        "saved": dict(a.answers.values_list("question_id", "selected"))})


@login_required
@require_POST
def api_answer(request, attempt_id):
    d = body(request)
    with transaction.atomic():
        a = locked(request, attempt_id)
        if a.status != S.IN_PROGRESS:
            return JsonResponse({"closed": True}, status=409)
        q = a.questions.filter(pk=d.get("question")).first()
        n = d.get("choice")
        if not q or type(n) is not int or not 1 <= n <= 4 or not getattr(q, f"option{n}"):
            return JsonResponse({"error": "invalid"}, status=400)
        Answer.objects.update_or_create(attempt=a, question=q, defaults={"selected": n})
    return JsonResponse({"ok": True})


@login_required
@require_POST
def api_violation(request, attempt_id):
    kind = body(request).get("kind")
    if kind not in ("tab_hidden", "window_blur", "copy_paste"):
        return JsonResponse({"error": "invalid"}, status=400)
    with transaction.atomic():
        a = locked(request, attempt_id)
        if a.status != S.IN_PROGRESS:
            return JsonResponse({"closed": True}, status=409)
        Violation.objects.create(attempt=a, kind=kind, ip=request.META.get("REMOTE_ADDR"),
                                 user_agent=request.META.get("HTTP_USER_AGENT", "")[:300])
        Attempt.objects.filter(pk=a.pk).update(violations=F("violations") + 1)
        a.refresh_from_db()
        if a.violations >= a.exam.max_violations:
            finalize(a, S.DISQUALIFIED)
    return JsonResponse({"violations": a.violations, "max": a.exam.max_violations,
                         "closed": a.status != S.IN_PROGRESS})


@login_required
@require_POST
def api_submit(request, attempt_id):
    with transaction.atomic():
        a = locked(request, attempt_id)
        if a.status == S.IN_PROGRESS:
            finalize(a, S.SUBMITTED)
    return JsonResponse({"redirect": reverse("result", args=[a.pk])})


def review_rows(a):
    answers = dict(a.answers.values_list("question_id", "selected"))
    rows = []
    for q in a.questions.all():
        sel = answers.get(q.pk)
        opts = [(n, t, n == q.correct, n == sel)
                for n, t in enumerate([q.option1, q.option2, q.option3, q.option4], 1) if t]
        rows.append({"q": q, "opts": opts, "sel": sel})
    return rows


@login_required
def result(request, attempt_id):
    a = get_object_or_404(Attempt.objects.select_related("exam"), pk=attempt_id, user=request.user)
    if a.status == S.IN_PROGRESS:
        return redirect("take", a.pk)
    ctx = {"a": a, "open": a.exam.results_open()}
    if ctx["open"]:  # تا زمان اعلام، هیچ نمره یا جزئیاتی به دانش‌آموز نمی‌رسد
        ctx.update(wrong=a.answered - a.correct, blank=a.total - a.answered, log=a.violation_log.all(),
                   rows=review_rows(a) if a.exam.show_answers else None)
    return render(request, "result.html", ctx)
