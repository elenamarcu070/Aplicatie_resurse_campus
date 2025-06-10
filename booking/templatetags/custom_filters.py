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