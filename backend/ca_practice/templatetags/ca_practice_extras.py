from django import template
from django.utils.html import conditional_escape
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter(name="break_every_words")
def break_every_words(value, words_per_line=5):
    """
    Insert <br> after every N words for compact diagram labels.
    """
    if value is None:
        return ""

    try:
        n = int(words_per_line)
    except (ValueError, TypeError):
        n = 5

    text = conditional_escape(value)
    words = str(text).split()
    if not words or n <= 0:
        return text

    lines = [" ".join(words[i : i + n]) for i in range(0, len(words), n)]
    return mark_safe("<br>".join(lines))

