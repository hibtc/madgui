Coding conventions
------------------

In general, follow the style of the surrounding code. More precisely:

- Follow `PEP 8`_ and `PEP 257`_.
- Add sphinx_ style docstrings for all modules, classes, functions
- Document user-relevant changes in the file ``CHANGES.rst``

I highly recommend to also:

- watch Kevlin Henney's `Seven ineffective Coding Habits of Many Programmers`_
- type ``import this`` in a python shell and appreciate

.. _PEP 8: http://www.python.org/dev/peps/pep-0008/
.. _PEP 257: http://www.python.org/dev/peps/pep-0257/
.. _sphinx: http://sphinx-doc.org/
.. _Seven ineffective Coding Habits of Many Programmers: https://www.youtube.com/watch?v=ZsHMHukIlJY


**Spaces:**

I feel like this deserves an extra section because I see it done wrong so
often. It is best to configure your text editor to take care of the following:

- Use spaces, not tabs! (This is important for consistent spacing across
  different editor settings and in particular in the context of python to
  avoid ``IndentationError``.)
- indentation is always 4 spaces
- avoid trailing spaces
- files end with a single newline character (Some editors such as vim do this
  by default)
- unix line endings
- no more than 80 columns line length (reading becomes hard at about 60)

These rules are designed to **avoid ambiguity** and some of the most common
reasons to add noise in commit diffs due to incidental whitespace changes that
have nothing to do with what the commit is actually trying to do.

    In the face of ambiguity, refuse the temptation to guess.

    There should be one-- and preferably only one --obvious way to do it.


**Naming:**

Altough the current code base is not entirely consistent, all new code should
follow these rules:

- ``ClassNames``
- ``function_names`` and methods
- ``variable_names`` and properties
- ``_private_variables`` and methods
- ``__special_methods__``
- ``GLOBAL_CONSTANTS`` (only constants!)
- PyQt class method overrides and their parameters, as well as child objects
  of widgets are in ``lowerCamelCase``


**Breaking statements***

When breaking a statement over multiple lines, it is best formatted such that
it becomes invariant with respect to refactorings.

If you don't know what this means, I recommend watching Kevlin Henney's `Seven
ineffective Coding Habits of Many Programmers`_.


**Version control:**

Commits should be reversible, independent units if possible. Use descriptive
titles and also add an explaining commit message unless the modification is
trivial. See also: `A Note About Git Commit Messages`_.

.. _`A Note About Git Commit Messages`: http://tbaggery.com/2008/04/19/a-note-about-git-commit-messages.html
