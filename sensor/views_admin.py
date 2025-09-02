from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
from django.shortcuts import render, redirect, get_object_or_404
from .models import ChamberAccess

def is_manager(user):
    return user.is_superuser   # only managers can access

CHAMBERS = [
    ("ch1", "Chamber 1"),
    ("ch2", "Chamber 2"),
    ("ch3", "Chamber 3"),
]

@login_required
@user_passes_test(is_manager)
def user_list(request):
    users = User.objects.all().exclude(is_superuser=True)
    return render(request, "admin_users.html", {"users": users})


@login_required
@user_passes_test(is_manager)
def user_create(request):
    if request.method == "POST":
        username = (request.POST.get("username") or "").strip()
        raw_password = (request.POST.get("password") or "").strip()
        chambers = request.POST.getlist("chambers")

        # simple validation
        if not username or not raw_password:
            messages.error(request, "Username and password are required.")
            return render(request, "admin_user_form.html", {
                "chambers": CHAMBERS,
                "assigned": [],
                "editing_user": None,
            })

        if User.objects.filter(username=username).exists():
            messages.error(request, "Username already exists.")
            return render(request, "admin_user_form.html", {
                "chambers": CHAMBERS,
                "assigned": [],
                "editing_user": None,
            })

        # always hashed
        u = User.objects.create_user(username=username, password=raw_password)

        for ch in chambers:
            ChamberAccess.objects.create(user=u, chamber=ch)

        return redirect("user_list")

    return render(request, "admin_user_form.html", {
        "chambers": CHAMBERS,
        "assigned": [],
        "editing_user": None,
    })


@login_required
@user_passes_test(is_manager)
def user_edit(request, user_id):
    u = get_object_or_404(User, id=user_id)
    if request.method == "POST":
        chambers = request.POST.getlist("chambers")
        ChamberAccess.objects.filter(user=u).delete()
        for ch in chambers:
            ChamberAccess.objects.create(user=u, chamber=ch)
        return redirect("user_list")

    assigned = list(ChamberAccess.objects.filter(user=u).values_list("chamber", flat=True))
    return render(request, "admin_user_form.html", {
        "editing_user": u,      # pass user here
        "chambers": CHAMBERS,
        "assigned": assigned,
    })

@login_required
@user_passes_test(is_manager)
def user_delete(request, user_id):
    u = get_object_or_404(User, id=user_id)
    if request.method == "POST":
        u.delete()
        return redirect("user_list")
    return render(request, "confirm_delete.html", {"user": u})


from django.shortcuts import redirect

@login_required
def post_login_redirect(request):
    if request.user.is_superuser:
        return redirect("user_list")       # admin dashboard
    return redirect("home")       # normal user home

def _allowed_chambers_for(user):
    if user.is_superuser:
        return ["ch1", "ch2", "ch3"]
    return list(ChamberAccess.objects.filter(user=user).values_list("chamber", flat=True))

@login_required
def redirect_to_default_chamber(request):
    allowed = _allowed_chambers_for(request.user)
    if not allowed:
        # No access assigned → optional: show a friendly page or send to logout/login
        # return render(request, "no_chambers.html")  # if you have a template
        return redirect("logout")  # or choose any
    # Pick the first allowed chamber and go to the table page
    default_ch = allowed[0]
    return redirect("sensor_data_page", ch=default_ch)