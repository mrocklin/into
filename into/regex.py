from __future__ import absolute_import, division, print_function

import re

def normalize(r):
    """

    >>> normalize('\d*')  # doctest: +SKIP
    '^\d*$'

    >>> normalize('^\d*$')  # doctest: +SKIP
    '^\d*$'
    """
    return '^' + r.lstrip('^').rstrip('$') + '$'

class RegexDispatcher(object):
    """
    Regular Expression Dispatcher

    >>> f = RegexDispatcher('f')

    >>> f.register('\d*')               # doctest: +SKIP
    ... def parse_int(s):
    ...     return int(s)

    >>> f.register('\d*\.\d*')          # doctest: +SKIP
    ... def parse_float(s):
    ...     return float(s)

    Set priorities to break ties between multiple matches.
    Default priority is set to 10

    >>> f.register('\w*', priority=9)   # doctest: +SKIP
    ... def parse_str(s):
    ...     return s

    >>> f('123')                        # doctest: +SKIP
    123

    >>> f('123.456')                    # doctest: +SKIP
    123.456
    """
    def __init__(self, name):
        self.name = name
        self.funcs = dict()
        self.priorities = dict()


    def add(self, regex, func, priority=10):
        self.funcs[normalize(regex)] = func
        self.priorities[func] = priority

    def register(self, regex, priority=10):
        def _(func):
            self.add(regex, func, priority)
            return func
        return _

    def dispatch(self, s):
        funcs = [func for r, func in self.funcs.items() if re.match(r, s)]
        return self.dispatch_iter(funcs)

    def dispatch_iter(self, funcs):
        # return a list of the functions reverse sorted by priority
        # that match the pattern
        return sorted(funcs, key=self.priorities.get, reverse=True)

    def __call__(self, s, *args, **kwargs):
        for f in self.dispatch(s):
            try:
                return f(s, *args, **kwargs)
            except NotImplementedError:
                continue

        # can't find anything
        raise NotImplementedError("unable to match any regexes for dispatching")
