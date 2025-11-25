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



from django import template
register = template.Library()

@register.simple_tag
def is_future_interval(ora_start, ora_sfarsit, now_hour):
    # transformă în int ca să poată compara
    try:
        ora_s = int(str(ora_start).split(':')[0])
        ora_f = int(str(ora_sfarsit).split(':')[0])
        ora_now = int(str(now_hour).split(':')[0])
    except:
        return False

    # dacă intervalul trece peste miezul nopții
    if ora_f < ora_s:
        return True
    return ora_f > ora_now

