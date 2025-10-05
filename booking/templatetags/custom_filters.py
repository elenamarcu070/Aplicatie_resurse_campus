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
