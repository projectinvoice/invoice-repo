from django import template

register = template.Library()

@register.filter
def mul(value, arg):
    """Multiplie deux nombres"""
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return 0
