.. highlight:: bash

Proxy Settings
==============

If you are behind a proxy, you have to configure several tools that require
internet access to work with the proxy. This includes at least:

- pip
- git
- conda

If you have modestly recent versions of conda/pip and git, the easiest and
most reliable way to setup their proxy configurations is by entering the
following commands in the terminal::

    pip config --user set global.proxy "PROXYSERVER"

    conda config --set proxy_servers.http  "PROXYSERVER"
    conda config --set proxy_servers.https "PROXYSERVER"

    git config --global http.proxy  "PROXYSERVER"
    git config --global https.proxy "PROXYSERVER"

with ``PROXYSERVER`` taking the format::

    protocol://[username:password@]hostname:port

Specifically at HIT, the value must be as follows::

    http://USERNAME:PASSWORD@proxy.krz.uni-heidelberg.de:8080

with your windows login credentials. Note that at HIT the correct protocol is
``http://`` (not https) for both the http and the https config entries. Both
entries should be assigned identical values!

Verify that your configuration is correct by looking at the output of::

    conda config --show

    pip config --user list

    git config --global --list

If the above command lines do not work with your version of git/pip/conda,
make yourself a favor and update! If you cannot, see below for manual
configuration of these entries.


conda
~~~~~

The conda proxy settings can be defined in the ``.condarc`` file. On linux the
location of this file usually is ``~/.condarc``, on windows it usually lives
under ``C:\Users\USERNAME`` (or ``%HOMEDRIVE%%HOMEPATH%``). At HIT, these
settings should look as follows:

.. code-block:: yaml

    proxy_servers:
        http:  PROXYSERVER
        https: PROXYSERVER

with ``PROXYSERVER`` as above.


pip
~~~

The pip config file can live in several different locations depending on your
system. On linux, the path is usually ``~/.config/pip/pip.conf`` or
``~/.pip/pip.conf`` on older versions. On windows, it should be in
``%APPDATA%\pip\pip.ini`` or ``%HOME%\pip\pip.ini`` on older versions. Please
make sure that you have the correct path, before proceeding.

The file content should look like this:

.. code-block:: ini

    [global]
    proxy = PROXYSERVER

with ``PROXYSERVER`` as defined above.


git
~~~

The git configuration file is called ``.gitconfig``. On linux, it usually
lives directly in the home directory, i.e. ``~/.gitconfig``. On windows, the
location can differ based on which git installation is used. If you use the
standard git for windows, it is usually in ``%USERPROFILE%\.gitconfig``. You
can enter ``%USERPROFILE%`` in the explorer location bar to get there. The
content of this file should look as follows:

.. code-block:: ini

    [http]
        proxy = PROXYSERVER

    [https]
        proxy = PROXYSERVER
