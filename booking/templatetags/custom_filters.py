from django import template

register = template.Library()

@register.filter
def range_filter(start, end):
    return range(start, end)



@register.filter
def dict_get(dict_obj, key):
    return dict_obj.get(key)


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



# booking/templatetags/custom_filters.py
from django import template

register = template.Library()

@register.filter(name='get_item')
def get_item(mapping, key):
    """
    Safe get pentru dict-uri/nested dict-uri în template.
    Dacă nu găsește cheia, încearcă și varianta stringificată.
    Returnează None dacă nu există, ca să nu crape lanțul de filtre.
    """
    if mapping is None:
        return None
    try:
        # dict-like
        if hasattr(mapping, 'get'):
            if key in mapping:
                return mapping.get(key)
            # încearcă și str(key) (ex: chei date / int vs str)
            skey = str(key)
            return mapping.get(skey, None)
        # list/tuple index
        if isinstance(key, int) and hasattr(mapping, '__getitem__'):
            return mapping[key]
    except Exception:
        pass
    return None


@register.simple_tag
def is_future_interval(ora_start, ora_sfarsit, now_hour):
    """
    Consideră viitor:
      - orice interval din azi cu ora_sfarsit > now_hour
      - intervalele care trec peste miezul nopții (ex 22:00–01:00)
    """
    # extrage orele ca int (suportă "H", "H:M", obiecte time)
    def to_hour_int(v):
        s = str(v)
        # dacă e "HH:MM:SS" sau "HH:MM"
        if ':' in s:
            return int(s.split(':', 1)[0])
        return int(s)
    try:
        h_start = to_hour_int(ora_start)
        h_end   = to_hour_int(ora_sfarsit)
        h_now   = to_hour_int(now_hour)
    except Exception:
        return False

    # dacă trece în ziua următoare (ex 22→1), e încă viitor pe azi
    if h_end < h_start:
        return True
    # altfel, simplu: sfârșitul intervalului e după ora curentă
    return h_end > h_now


