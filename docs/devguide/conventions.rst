Coding conventions
------------------

In general, follow the style of the surrounding code.


**Coding:**

- Use spaces, not tabs! (important for consistent spacing across different
  editor settings and to avoid ``IndentationError``)
- avoid trailing spaces
- Follow PEP8_ and PEP257_.
- Add `sphinx`_ style docstrings for all modules, classes, functions
- Document user-relevant changes in the file ``CHANGES.rst``

.. _PEP8: http://www.python.org/dev/peps/pep-0008/
.. _PEP257: http://www.python.org/dev/peps/pep-0257/
.. _`sphinx`: http://sphinx-doc.org/

**Naming:**

Altough the current code base is not entirely consistent, all new code should
follow these rules:

- class names are in ``CamelCase``
- for method, member and variable names, stick to ``names_with_underscores`` as
  recommended by PEP8_
- PyQt class method overrides and their parameters, as well as child objects
  of widgets are in ``lowerCamelCase``

**Version control:**

Commits should be reversible, independent units if possible. Use descriptive
titles and also add an explaining commit message unless the modification is
trivial. See also: `A Note About Git Commit Messages`_.

.. _`A Note About Git Commit Messages`: http://tbaggery.com/2008/04/19/a-note-about-git-commit-messages.html
