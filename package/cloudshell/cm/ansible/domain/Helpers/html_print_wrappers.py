def _html_wrap(color, text):
    return "<span style='color: {}'=>{}</span>".format(color, text)


def warn_span(text):
    return _html_wrap("yellow", text)


def err_span(text):
    return _html_wrap("red", text)


def success_span(text):
    return _html_wrap("green", text)
