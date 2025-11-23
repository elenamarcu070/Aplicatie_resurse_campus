from django import template

register = template.Library()

@register.filter
def range_filter(start, end):
    return range(start, end)



@register.filter
def dict_get(dict_obj, key):
    return dict_obj.get(key)


@register.filter
def get_item(dictionary, key):
    return dictionary.get(key)

from booking.models import AdminCamin


@register.filter
def admin_telefon(email):
    try:
        admin = AdminCamin.objects.filter(email=email).first()
        return admin.telefon if admin and admin.telefon else "-"
    except Exception:
        return "-"


# booking/templatetags/custom_filters.py

from django import template

register = template.Library()

@register.filter
def two_digits(value):
    """
    Transformă 60 → "01", 75 → "01:15", etc.
    Dar pentru ore (0–23) va returna mereu două cifre.
    """
    try:
        value = int(value) % 24
        return f"{value:02d}"
    except:
        return value
@register.filter
def get_item(dictionary, key):
    """
    Pentru accesarea dicturilor în template:
    rezervari_dict|get_item:masina.id|get_item:zi
    """
    try:
        return dictionary.get(key)
    except:
        return None
