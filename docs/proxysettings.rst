Proxy Settings
==============

In order to further continue using the conda environment, some proxy configuration files are needed if you are working behind a firewall, which restricts the free download and upload of data.

First, open a text file and type the following::

    auto_update_conda: false

    proxy_servers:
      http: http://"Your username in the server":"Your password in the server"@"The name of the proxy"
      https: https://"Your username in the server":"Your password in the server"@"The name of the proxy

And save the document as .condarc in the SysDisc/User/"Your Username"/
directory for Windows. For Linux save it in your home directory.

Some of the applications won't be downloadable via conda install, so we also recommend installing pip::

  conda install pip

In the same way open a a text file and type::

  [global]
  proxy=http://"Your username in the server":"Your password in the server"@"The name of the proxy":8080

Save the document as pip.ini in SysDisc/User/"Your Username"/ directory (or in your home directory) and now you should also be able to use the command::

  pip install "Some app"

Note that you might have to refresh continuosly your web browser.
