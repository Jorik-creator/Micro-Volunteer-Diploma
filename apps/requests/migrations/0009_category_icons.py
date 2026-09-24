from django.db import migrations

# "paw" is not a Bootstrap icon: templates render an inline paw SVG for it
ICONS = {
    "produkty-ta-kharchuvannia": "bi-basket2",
    "medychna-dopomoha": "bi-capsule",
    "transport-i-peresuvannia": "bi-car-front",
    "prybyrannia-ta-pobut": "bi-bucket",
    "tekhnichna-dopomoha": "bi-phone",
    "navchannia-ta-konsultatsii": "bi-mortarboard",
    "tvaryny": "paw",
    "inshe": "bi-three-dots",
}


def set_icons(apps, schema_editor):
    Category = apps.get_model("requests", "Category")
    for slug, icon in ICONS.items():
        Category.objects.filter(slug=slug).update(icon=icon)


class Migration(migrations.Migration):
    dependencies = [
        ("requests", "0008_response_status_changed_at"),
    ]

    operations = [migrations.RunPython(set_icons, migrations.RunPython.noop)]
