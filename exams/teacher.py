import re

from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.contrib.auth.models import Group, User
from django.core.paginator import Paginator
from django.db.models import Avg, Count, F, Max, Min, ProtectedError, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

from .forms import ExamForm, QuestionForm
from .models import Answer, Attempt, Category, Exam, ExamBankRule, Question, Tag
from .views import review_rows

teacher_only = user_passes_test(lambda u: u.is_active and u.is_staff, login_url="login")


def ids(request, name):
    return [int(i) for i in request.POST.getlist(name) if i.isdigit()]


@teacher_only
def teacher_home(request):
    exams = Exam.objects.prefetch_related("allowed_groups").annotate(n=Count("attempts"), avg=Avg("attempts__score")).order_by("-id")
    kpi = Attempt.objects.aggregate(attempts=Count("id"), students=Count("user", distinct=True), avg=Avg("score"),
                                    live=Count("id", filter=Q(status="in_progress")))
    recent = Attempt.objects.select_related("user", "exam").order_by("-started_at")[:8]
    return render(request, "teacher_home.html", {"sec": "dash", "exams": exams, "kpi": kpi, "recent": recent,
                                                 "bank_count": Question.objects.filter(exam__isnull=True).count()})


@teacher_only
def teacher_exam(request, exam_id):
    e = get_object_or_404(Exam, pk=exam_id)
    attempts = e.attempts.select_related("user").order_by("-score", "started_at")
    agg = attempts.exclude(status="in_progress").aggregate(avg=Avg("score"), hi=Max("score"), lo=Min("score"), n=Count("id"))
    through = Attempt.questions.through
    asked = dict(through.objects.filter(attempt__exam=e).exclude(attempt__status="in_progress")
                 .values_list("question_id").annotate(n=Count("id")))
    right = dict(Answer.objects.filter(attempt__exam=e, selected=F("question__correct"))
                 .exclude(attempt__status="in_progress").values_list("question_id").annotate(n=Count("id")))
    qstats = sorted(({"q": q, "asked": asked[q.pk], "pct": round(100 * right.get(q.pk, 0) / asked[q.pk])}
                     for q in Question.objects.filter(pk__in=asked)), key=lambda r: r["pct"])
    absent = User.objects.filter(groups__in=e.allowed_groups.all()).exclude(attempts__exam=e).distinct()
    return render(request, "teacher_exam.html", {"sec": "dash", "e": e, "attempts": attempts, "agg": agg,
                                                 "qstats": qstats, "absent": absent})


@teacher_only
def teacher_attempt(request, attempt_id):
    a = get_object_or_404(Attempt.objects.select_related("exam", "user"), pk=attempt_id)
    return render(request, "teacher_attempt.html", {"sec": "dash", "a": a, "rows": review_rows(a), "log": a.violation_log.all(),
                                                    "wrong": a.answered - a.correct, "blank": a.total - a.answered})


# ---------------- آزمون‌ها ----------------
@teacher_only
def teacher_exams(request):
    exams = Exam.objects.prefetch_related("allowed_groups").annotate(n=Count("attempts", distinct=True)).order_by("-id")
    return render(request, "teacher_exams.html", {"sec": "exams", "exams": exams})


@teacher_only
def teacher_exam_form(request, exam_id=None):
    exam = get_object_or_404(Exam, pk=exam_id) if exam_id else None
    form = ExamForm(request.POST or None, instance=exam)
    if request.method == "POST" and form.is_valid():
        saved = form.save()
        messages.success(request, "آزمون ذخیره شد." if exam else "آزمون ساخته شد؛ حالا سؤال‌ها را اضافه کنید.")
        return redirect("teacher_exam_edit", saved.pk)
    ctx = {"sec": "exams", "form": form, "exam": exam}
    if exam:
        ctx.update(fixed=exam.questions.all(), rules=exam.bank_rules.select_related("category"),
                   categories=Category.objects.annotate(n=Count("questions", filter=Q(questions__exam__isnull=True))),
                   bank_total=Question.objects.filter(exam__isnull=True).count(), attempts=exam.attempts.count(),
                   multi_group=exam.allowed_groups.count() > 1)
    return render(request, "teacher_exam_form.html", ctx)


@teacher_only
@require_POST
def teacher_exam_delete(request, exam_id):
    exam = get_object_or_404(Exam, pk=exam_id)
    if exam.attempts.exists():
        messages.error(request, "این آزمون شرکت‌کننده دارد و حذف نمی‌شود (سابقه دائمی است). می‌توانید آن را غیرفعال کنید.")
        return redirect("teacher_exam_edit", exam.pk)
    exam.delete()
    messages.success(request, "آزمون حذف شد.")
    return redirect("teacher_exams")


@teacher_only
@require_POST
def teacher_exam_qremove(request, exam_id, question_id):
    q = get_object_or_404(Question, pk=question_id, exam_id=exam_id)
    try:
        q.delete()
        messages.success(request, "سؤال از آزمون برداشته شد (در بانک می‌ماند).")
    except ProtectedError:
        messages.error(request, "این سؤال قبلاً پاسخ داده شده و حذف نمی‌شود.")
    return redirect("teacher_exam_edit", exam_id)


@teacher_only
@require_POST
def teacher_rule_add(request, exam_id):
    exam = get_object_or_404(Exam, pk=exam_id)
    cat = Category.objects.filter(pk=request.POST.get("category")).first()  # خالی = کل بانک
    try:
        count = int(request.POST.get("count", ""))
    except ValueError:
        count = 0
    rule = ExamBankRule(exam=exam, category=cat, count=count)
    if count < 1:
        messages.error(request, "تعداد سؤال را وارد کنید.")
    elif exam.bank_rules.filter(category=cat).exists():
        messages.error(request, "برای این دسته‌بندی قبلاً قاعده ساخته‌اید؛ اول آن را حذف کنید.")
    else:
        try:
            rule.clean()
            rule.save()
            messages.success(request, "قاعدهٔ سؤال تصادفی اضافه شد.")
        except Exception as e:  # ValidationError
            messages.error(request, " ".join(getattr(e, "messages", [str(e)])))
    return redirect("teacher_exam_edit", exam.pk)


@teacher_only
@require_POST
def teacher_rule_delete(request, exam_id, rule_id):
    get_object_or_404(ExamBankRule, pk=rule_id, exam_id=exam_id).delete()
    messages.success(request, "قاعده حذف شد.")
    return redirect("teacher_exam_edit", exam_id)


# ---------------- گروه‌ها (کلاس‌ها) ----------------
@teacher_only
def teacher_groups(request):
    if request.method == "POST":
        name = request.POST.get("name", "").strip()[:150]
        if not name:
            messages.error(request, "نام گروه را بنویسید.")
        elif Group.objects.filter(name__iexact=name).exists():
            messages.error(request, "گروهی با این نام وجود دارد.")
        else:
            g = Group.objects.create(name=name)
            messages.success(request, "گروه ساخته شد؛ حالا دانش‌آموزان را اضافه کنید.")
            return redirect("teacher_group", g.pk)
        return redirect("teacher_groups")
    groups = Group.objects.annotate(n=Count("user", filter=Q(user__is_staff=False), distinct=True),
                                    exams=Count("exam", distinct=True)).order_by("name")
    return render(request, "teacher_groups.html", {"sec": "groups", "groups": groups})


@teacher_only
def teacher_group(request, group_id):
    group = get_object_or_404(Group, pk=group_id)
    students = User.objects.filter(is_staff=False)
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "members":
            picked = ids(request, "u")
            group.user_set.remove(*group.user_set.filter(is_staff=False).exclude(pk__in=picked))
            group.user_set.add(*students.filter(pk__in=picked))
            messages.success(request, "اعضای گروه ذخیره شد.")
        elif action == "rename":
            name = request.POST.get("name", "").strip()[:150]
            if not name:
                messages.error(request, "نام گروه خالی است.")
            elif Group.objects.filter(name__iexact=name).exclude(pk=group.pk).exists():
                messages.error(request, "گروهی با این نام وجود دارد.")
            else:
                group.name = name
                group.save()
                messages.success(request, "نام گروه تغییر کرد.")
        elif action == "delete":
            if group.exam_set.exists():  # حذف گروه، آزمون را برای همه باز می‌کرد
                messages.error(request, "این گروه در آزمون‌ها استفاده شده؛ اول گروه آن آزمون‌ها را عوض کنید.")
            else:
                group.delete()
                messages.success(request, "گروه حذف شد.")
                return redirect("teacher_groups")
        return redirect("teacher_group", group.pk)
    members = set(group.user_set.values_list("pk", flat=True))
    rows = [{"u": u, "member": u.pk in members, "others": [g.name for g in u.groups.all() if g.pk != group.pk]}
            for u in students.prefetch_related("groups").order_by("last_name", "first_name", "username")]
    return render(request, "teacher_group.html", {"sec": "groups", "group": group, "rows": rows, "member_count": len(members),
                                                  "exams": group.exam_set.all()})


@teacher_only
def teacher_students(request):
    users = (User.objects.filter(is_staff=False).prefetch_related("groups").annotate(n=Count("attempts", distinct=True))
             .order_by("last_name", "first_name", "username"))
    return render(request, "teacher_students.html", {"sec": "students", "users": users})


# ---------------- بانک سؤال ----------------
def norm_tags(raw):
    """«الف، ب, ج» → ['الف','ب','ج'] بدون تکرار و بدون #"""
    out = []
    for t in re.split(r"[,،;؛\n]+", raw or ""):
        t = re.sub(r"\s+", " ", t.strip().lstrip("#")).strip()[:60]
        if t and t.lower() not in [o.lower() for o in out]:
            out.append(t)
    return out


def get_tags(names):
    tags = []
    for n in names:
        t = Tag.objects.filter(name__iexact=n).first() or Tag.objects.create(name=n)
        tags.append(t)
    return tags


COPY_FIELDS = ("text", "option1", "option2", "option3", "option4", "correct")


def copy_to_exam(bank_q, exam):
    """کپی سؤال بانک در آزمون (اگر قبلاً نبوده). برمی‌گرداند: True اگر اضافه شد."""
    dup = Q(origin=bank_q) | (Q(pk=bank_q.origin_id) if bank_q.origin_id else Q(pk__in=[]))
    if exam.questions.filter(dup).exists():
        return False
    Question.objects.create(exam=exam, origin=bank_q, order=exam.questions.count() + 1,
                            **{f: getattr(bank_q, f) for f in COPY_FIELDS})
    return True


@teacher_only
def teacher_bank(request):
    base = Question.objects.filter(exam__isnull=True)
    if request.method == "POST":
        picked = list(base.filter(pk__in=ids(request, "q")))
        action = request.POST.get("action")
        back = request.POST.get("back") or request.path
        if not picked:
            messages.error(request, "هیچ سؤالی انتخاب نشده است.")
        elif action == "import":
            exam = Exam.objects.filter(pk=request.POST.get("exam") or 0).first()
            if not exam:
                messages.error(request, "آزمون مقصد را انتخاب کنید.")
            else:
                added = sum(copy_to_exam(b, exam) for b in picked)
                messages.success(request, f"{added} سؤال به آزمون «{exam.title}» اضافه شد.")
        elif action in ("cat_add", "cat_remove"):
            cat = Category.objects.filter(pk=request.POST.get("category") or 0).first()
            if not cat:
                messages.error(request, "دسته‌بندی را انتخاب کنید.")
            else:
                for q in picked:
                    (q.categories.add if action == "cat_add" else q.categories.remove)(cat)
                messages.success(request, f"دسته‌بندی «{cat.name}» برای {len(picked)} سؤال {'افزوده' if action == 'cat_add' else 'برداشته'} شد.")
        elif action == "tag_add":
            names = norm_tags(request.POST.get("tags"))
            if not names:
                messages.error(request, "تگ را بنویسید.")
            else:
                tags = get_tags(names)
                for q in picked:
                    q.tags.add(*tags)
                messages.success(request, f"تگ برای {len(picked)} سؤال افزوده شد.")
        elif action == "delete":
            gone = 0
            for q in picked:
                try:
                    q.delete()
                    gone += 1
                except ProtectedError:
                    messages.error(request, "بخشی از سؤال‌ها در آزمون‌های برگزارشده استفاده شده‌اند و حذف نشدند.")
            if gone:
                messages.success(request, f"{gone} سؤال حذف شد.")
        return redirect(back if back.startswith("/") else request.path)

    qs = base.prefetch_related("categories", "tags").select_related("origin__exam").order_by("-id")
    cat = Category.objects.filter(pk=request.GET.get("cat") or 0).first()
    tag = Tag.objects.filter(pk=request.GET.get("tag") or 0).first()
    text = request.GET.get("q", "").strip()
    nocat = request.GET.get("cat") == "none"
    if cat:
        qs = qs.filter(categories=cat)
    elif nocat:
        qs = qs.filter(categories__isnull=True)
    if tag:
        qs = qs.filter(tags=tag)
    if text:
        qs = qs.filter(Q(text__icontains=text) | Q(tags__name__icontains=text)).distinct()
    page = Paginator(qs, 25).get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)
    return render(request, "teacher_bank.html", {
        "sec": "banks", "page": page, "total": base.count(), "found": page.paginator.count, "qs": params.urlencode(),
        "cats": Category.objects.annotate(n=Count("questions", filter=Q(questions__exam__isnull=True))),
        "uncat": base.filter(categories__isnull=True).count(), "cat": cat, "nocat": nocat, "tag": tag, "text": text,
        "tags": Tag.objects.filter(questions__exam__isnull=True).distinct(),
        "exams": Exam.objects.order_by("-id"), "target": Exam.objects.filter(pk=request.GET.get("exam") or 0).first(),
        "back": request.get_full_path()})


@teacher_only
def teacher_question_form(request, question_id=None):
    q = get_object_or_404(Question, pk=question_id, exam__isnull=True) if question_id else None
    initial = {"tags": "، ".join(t.name for t in q.tags.all())} if q else {}
    if not q and request.GET.get("cat"):
        initial["categories"] = [request.GET["cat"]]
    if not q and request.GET.get("exam"):
        initial["exam"] = request.GET["exam"]
    form = QuestionForm(request.POST or None, instance=q, initial=initial)
    if request.method == "POST" and form.is_valid():
        saved = form.save()
        saved.tags.set(get_tags(norm_tags(form.cleaned_data["tags"])))
        exam = form.cleaned_data.get("exam")
        if exam and copy_to_exam(saved, exam):
            messages.success(request, f"سؤال ذخیره و به آزمون «{exam.title}» اضافه شد.")
            return redirect("teacher_exam_edit", exam.pk)
        messages.success(request, "سؤال ذخیره شد.")
        if "again" in request.POST:
            return redirect("teacher_question_new")
        return redirect("teacher_bank")
    return render(request, "teacher_question_form.html", {
        "sec": "banks", "form": form, "q": q, "all_tags": Tag.objects.all(), "cats": Category.objects.all()})


@teacher_only
@require_POST
def teacher_categories(request):
    action, name = request.POST.get("action"), request.POST.get("name", "").strip()[:80]
    if action == "add":
        if not name:
            messages.error(request, "نام دسته‌بندی را بنویسید.")
        elif Category.objects.filter(name__iexact=name).exists():
            messages.error(request, "این دسته‌بندی از قبل هست.")
        else:
            Category.objects.create(name=name, order=Category.objects.count() + 1)
            messages.success(request, "دسته‌بندی ساخته شد.")
    elif action == "delete":
        cat = get_object_or_404(Category, pk=request.POST.get("id") or 0)
        if cat.exambankrule_set.exists():
            messages.error(request, "این دسته‌بندی در قاعدهٔ سؤال تصادفی یک آزمون استفاده شده است.")
        else:
            cat.delete()
            messages.success(request, "دسته‌بندی حذف شد؛ سؤال‌هایش در بانک می‌مانند.")
    return redirect("teacher_bank")


# ---------------- خروجی اکسل ----------------
HEAD = ["نام", "نام خانوادگی", "نام کاربری", "درصد", "درست", "غلط", "بی‌پاسخ", "کل سؤال", "وضعیت", "تخلف", "زمان شروع"]


def safe(v):  # متن‌هایی که با = + - @ شروع شوند در اکسل فرمول حساب می‌شوند
    v = "" if v is None else str(v)
    return "'" + v if v[:1] in ("=", "+", "-", "@") else v


def fill_sheet(ws, e):
    ws.sheet_view.rightToLeft = True
    ws.append(HEAD)
    for c in ws[1]:
        c.font, c.fill, c.alignment = Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor="0E1A36"), Alignment(horizontal="center")
    for a in e.attempts.select_related("user").order_by("user__last_name", "user__first_name"):
        u, done = a.user, a.status != "in_progress"
        ws.append([safe(u.first_name), safe(u.last_name), safe(u.username), a.score if done else None,
                   a.correct if done else None, a.answered - a.correct if done else None,
                   a.total - a.answered if done else None, a.total, a.get_status_display(), a.violations,
                   timezone.localtime(a.started_at).replace(tzinfo=None)])
    for u in User.objects.filter(groups__in=e.allowed_groups.all()).exclude(attempts__exam=e).distinct():
        ws.append([safe(u.first_name), safe(u.last_name), safe(u.username), None, None, None, None, None, "شرکت نکرد", None, None])
    for row in ws.iter_rows(min_row=2):
        row[3].number_format, row[10].number_format = "0.0", "yyyy/mm/dd hh:mm"
    for col, w in zip("ABCDEFGHIJK", (16, 18, 16, 9, 8, 8, 10, 10, 22, 8, 18)):
        ws.column_dimensions[col].width = w
    ws.freeze_panes = "A2"


def xlsx_response(wb, name):
    r = HttpResponse(content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    r["Content-Disposition"] = f'attachment; filename="{name}.xlsx"'
    wb.save(r)
    return r


def sheet_title(e):
    return (re.sub(r"[\[\]:*?/\\]", "", e.title)[:24] + f"-{e.pk}")


@teacher_only
def teacher_xlsx(request, exam_id):
    e = get_object_or_404(Exam, pk=exam_id)
    wb = Workbook()
    wb.active.title = sheet_title(e)
    fill_sheet(wb.active, e)
    return xlsx_response(wb, f"exam-{e.pk}")


@teacher_only
def teacher_xlsx_all(request):
    wb, first = Workbook(), True
    for e in Exam.objects.order_by("id"):
        ws = wb.active if first else wb.create_sheet()
        ws.title, first = sheet_title(e), False
        fill_sheet(ws, e)
    return xlsx_response(wb, "all-exams")
