"""
Portfolio demo data (ROADMAP stage 9).

`seed()` builds a small but complete world: three one-click demo accounts
(volunteer, recipient, moderator), a few ordinary users, requests in every
state, a conversation, reviews, a pending verification, a request waiting
for premoderation and a report. Dates are relative to "now", so the demo
never looks stale. `reset_daily()` wipes and re-seeds it once a day.
"""

import random
from datetime import timedelta

from django.contrib.auth.models import Group
from django.core.management import call_command
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.permissions import MODERATORS_GROUP
from apps.conversations import services as chat
from apps.conversations.models import Conversation
from apps.moderation.models import InviteCode, Report, VerificationRequest
from apps.requests.models import Category, HelpRequest, Response
from apps.reviews.models import Review

RESET_EVERY = timedelta(hours=24)

KYIV = (50.4501, 30.5234)
LVIV = (49.8397, 24.0297)

H = HelpRequest.HelpFormat
S = HelpRequest.Status


def _user(username, first, last, user_type, *, demo=False, verified=False, lat_lon=KYIV, **extra):
    user = User(
        username=username,
        email=f"{username}@demo.microvolunteer.invalid",
        first_name=first,
        last_name=last,
        user_type=user_type,
        is_demo=demo,
        is_verified=verified,
        email_verified_at=timezone.now(),
        terms_accepted_at=timezone.now(),
        latitude=lat_lon[0],
        longitude=lat_lon[1],
        **extra,
    )
    user.set_unusable_password()  # demo users log in only via the demo buttons
    user.save()
    return user


def _jitter(point, rng):
    return point[0] + rng.uniform(-0.03, 0.03), point[1] + rng.uniform(-0.05, 0.05)


def _request(
    recipient,
    category,
    title,
    description,
    *,
    when,
    status=S.ACTIVE,
    rng,
    city=KYIV,
    address="вул. Хрещатик, 1",
    **extra,
):
    lat, lon = _jitter(city, rng)
    help_request = HelpRequest.objects.create(
        recipient=recipient,
        category=category,
        title=title,
        description=description,
        needed_date=timezone.now() + when,
        city="" if extra.get("help_format") == H.REMOTE else ("Львів" if city == LVIV else "Київ"),
        address=address if extra.get("help_format") != H.REMOTE else "",
        latitude=None if extra.get("help_format") == H.REMOTE else lat,
        longitude=None if extra.get("help_format") == H.REMOTE else lon,
        status=status,
        published_at=None if status in (S.DRAFT, S.PENDING_MODERATION) else timezone.now(),
        completed_at=timezone.now() - timedelta(days=2) if status == S.COMPLETED else None,
        **extra,
    )
    return help_request


def _respond(help_request, volunteer, message):
    return Response.objects.create(help_request=help_request, volunteer=volunteer, message=message)


def wipe():
    """Remove everything except superusers, categories and invite codes."""
    User.objects.filter(is_superuser=False).delete()  # cascades to requests, chats, reviews...


@transaction.atomic
def seed(seed_value=42):
    rng = random.Random(seed_value)
    if not Category.objects.exists():
        call_command("loaddata", "initial_categories", verbosity=0)
    cat = {c.slug: c for c in Category.objects.all()}
    food = cat.get("produkty-ta-kharchuvannia")
    med = cat.get("medychna-dopomoha")
    transport = cat.get("transport-i-peresuvannia")
    home = cat.get("prybyrannia-ta-pobut")
    tech = cat.get("tekhnichna-dopomoha")
    pets = cat.get("tvaryny")

    V, R = User.UserType.VOLUNTEER, User.UserType.RECIPIENT

    # One-click demo accounts
    anna = _user(
        "demo.volunteer", "Анна", "Коваль", V, demo=True, verified=True, phone="+380501110001"
    )
    maria = _user("demo.recipient", "Марія", "Іваненко", R, demo=True, phone="+380501110002")
    oleh = _user("demo.moderator", "Олег", "Бондар", V, demo=True, verified=True)
    oleh.groups.add(Group.objects.get_or_create(name=MODERATORS_GROUP)[0])

    # Ordinary users
    iryna = _user("iryna.s", "Ірина", "Савчук", V, verified=True)
    taras = _user("taras.m", "Тарас", "Мельник", V)
    dmytro = _user("dmytro.l", "Дмитро", "Лисенко", V, verified=True, lat_lon=LVIV)
    halyna = _user("halyna.p", "Галина", "Петренко", R)
    sofia = _user("sofia.k", "Софія", "Кравець", R, lat_lon=LVIV)
    petro = _user("petro.new", "Петро", "Новак", R)

    for volunteer, cats, bio in (
        (anna, [food, med, pets], "Студентка медуніверситету, маю вільні вечори."),
        (iryna, [home, food], "Працюю віддалено, допомагаю сусідам по Оболоні."),
        (dmytro, [transport, tech], "Маю авто, можу підвезти до лікаря."),
        (taras, [tech], "Налаштую телефон, Дію чи ноутбук."),
    ):
        profile = volunteer.volunteer_profile
        profile.bio = bio
        profile.radius_km = 20
        profile.save()
        profile.categories.set([c for c in cats if c])

    # Active requests for the volunteer to browse
    _request(
        maria,
        med,
        "Забрати ліки з аптеки",
        "Потрібно забрати рецептурні ліки в аптеці на розі й занести до під'їзду.",
        when=timedelta(days=1, hours=3),
        help_format=H.DOORSTEP,
        urgency="high",
        rng=rng,
    )
    _request(
        halyna,
        food,
        "Купити продукти на тиждень",
        "Список невеликий: хліб, молоко, крупи, овочі. Гроші віддам готівкою за чеком.",
        when=timedelta(days=2),
        help_format=H.DOORSTEP,
        duration="1h",
        rng=rng,
    )
    _request(
        halyna,
        home,
        "Допомогти повісити штори",
        "Мені 78 років, самій не дістати до карниза. Потрібна одна людина на пів години.",
        when=timedelta(days=3),
        help_format=H.HOME_VISIT,
        duration="30min",
        rng=rng,
    )
    _request(
        sofia,
        transport,
        "Провести до поліклініки",
        "Потрібен супровід до поліклініки й назад, погано бачу.",
        when=timedelta(days=1, hours=20),
        help_format=H.PUBLIC_PLACE,
        city=LVIV,
        address="вул. Городоцька, 15",
        urgency="high",
        rng=rng,
    )
    _request(
        sofia,
        tech,
        "Налаштувати Дію на новому телефоні",
        "Купила новий телефон, не можу увійти в Дію.",
        when=timedelta(days=4),
        help_format=H.REMOTE,
        duration="30min",
        rng=rng,
    )
    walk = _request(
        maria,
        pets,
        "Вигуляти собаку",
        "Собака спокійна, лабрадор. Я на лікарняному ще тиждень.",
        when=timedelta(hours=20),
        help_format=H.DOORSTEP,
        volunteers_needed=1,
        rng=rng,
    )
    _respond(walk, iryna, "Можу ввечері після 18:00.")
    _respond(walk, taras, "Живу поруч, можу вранці.")

    # In progress with a conversation (Анна is accepted)
    groceries = _request(
        maria,
        food,
        "Донести воду на 5-й поверх",
        "Потрібно купити й занести 4 бутлі води, ліфта немає.",
        when=timedelta(days=1),
        help_format=H.HOME_VISIT,
        rng=rng,
    )
    response = _respond(groceries, anna, "Можу завтра о 17:00.")
    response.status = Response.Status.ACCEPTED
    response.save()
    groceries.status = S.IN_PROGRESS
    groceries.save()
    conversation = chat.open_for(response)
    for sender, text in (
        (maria, "Дякую, що відгукнулися! Код домофону скажу, коли під'їдете."),
        (anna, "Добре, буду о 17:00. Взяти воду в АТБ поруч?"),
        (maria, "Так, там найближче. Гроші віддам готівкою."),
    ):
        chat.send(Conversation.objects.get(pk=conversation.pk), sender, text)

    # Awaiting confirmation
    cleaning = _request(
        halyna,
        home,
        "Винести старі меблі",
        "Стара шафа, розібрана. Потрібно двоє людей.",
        when=-timedelta(hours=5),
        help_format=H.HOME_VISIT,
        volunteers_needed=2,
        rng=rng,
    )
    for volunteer in (iryna, dmytro):
        r = _respond(cleaning, volunteer, "Буду.")
        r.status = Response.Status.ACCEPTED
        r.done_at = timezone.now() - timedelta(hours=2)
        r.save()
    cleaning.status = S.AWAITING_CONFIRMATION
    cleaning.save()

    # Completed with a published review pair and one awaiting Maria's rating
    for title, volunteer, rating, tags, comment in (
        ("Налаштувати смартфон", taras, 5, ["polite", "in_touch"], "Терпляче все пояснив, дякую!"),
        ("Супровід на прогулянку", anna, 5, ["punctual", "careful"], "Анна дуже уважна."),
    ):
        done = _request(
            maria,
            tech if "смартфон" in title else home,
            title,
            "Виконано.",
            when=-timedelta(days=3),
            status=S.COMPLETED,
            help_format=H.HOME_VISIT,
            rng=rng,
        )
        r = _respond(done, volunteer, "Допоможу.")
        r.status = Response.Status.ACCEPTED
        r.done_at = timezone.now() - timedelta(days=3)
        r.save()
        if volunteer is taras:
            Review.objects.create(
                author=maria,
                target=taras,
                help_request=done,
                rating=rating,
                tags=tags,
                comment=comment,
                published_at=timezone.now(),
            )
            Review.objects.create(
                author=taras,
                target=maria,
                help_request=done,
                rating=5,
                tags=["clear_request", "welcoming"],
                published_at=timezone.now(),
            )
        else:
            # Anna already rated Maria; Maria still has to rate Anna (blind exchange demo)
            Review.objects.create(
                author=anna,
                target=maria,
                help_request=done,
                rating=5,
                tags=["welcoming"],
                comment="Приємно було допомогти.",
            )

    # Moderation queue content
    _request(
        petro,
        food,
        "Потрібна допомога з покупками",
        "Перший запит нового користувача — чекає на перевірку модератора.",
        when=timedelta(days=2),
        status=S.PENDING_MODERATION,
        help_format=H.DOORSTEP,
        rng=rng,
    )
    VerificationRequest.objects.create(
        user=taras,
        city="Київ",
        about="Програміст, хочу допомагати літнім людям з технікою.",
        contact_link="https://github.com/",
        video_call_ok=True,
    )
    Report.objects.create(
        reporter=halyna,
        target=petro,
        reason=Report.Reason.SPAM,
        comment="Пише в розмові незрозумілі посилання.",
    )
    InviteCode.objects.get_or_create(
        code="DEMOCODE42", defaults={"organization": "ГО «Добросусідство» (демо)", "max_uses": 1000}
    )
    return {"users": User.objects.count(), "requests": HelpRequest.objects.count()}


def reset_daily(now=None):
    """Periodic task: re-seed the demo once a day when DEMO_MODE is on."""
    from django.conf import settings

    if not settings.DEMO_MODE:
        return "off"
    now = now or timezone.now()
    oldest = User.objects.filter(is_demo=True).order_by("date_joined").first()
    if oldest and now - oldest.date_joined < RESET_EVERY:
        return 0
    wipe()
    seed()
    return 1
