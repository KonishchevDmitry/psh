psh allows you to spawn processes in Unix shell-style way.

Unix shell is very convenient for spawning processes, connecting them into
pipes, etc., but it has a very limited language which is often not suitable
for writing complex programs. Python is a very flexible and reach language
which is used in a wide variety of application domains, but its standard
subprocess module is very limited. psh combines the power of Python language
and an elegant shell-style way to execute processes.


Examples
--------

Print output of ``echo -n "text"``:

.. code:: python

    from psh import sh
    print sh.echo("-n", "text").execute().stdout()


Get a list of all available network interfaces (``ifconfig | egrep -o "^[^[:space:]:]+"``):

.. code:: python

    from psh import sh
    interfaces = [ iface.rstrip("\n") for iface in sh.ifconfig() | sh.egrep("-o", "^[^[:space:]:]+") ]

Check free disk space on remote host *myserver.com*:

.. code:: python

    import re
    from psh import sh

    # ssh myserver.com 'df | egrep "^/dev/"'
    with sh.ssh("myserver.com", sh.df() | sh.egrep("^/dev/"), _shell = True) as ssh:
        for line in ssh:
            match = re.search(r"^(/dev/[^\s+]+)\s+(?:[^\s]+\s+){3}(\d+)%\s+(/.*)$", line.rstrip("\n"))
            device, used, mount_point = match.groups()
            if int(used) > 80:
                print "{0} ({1}) ran out of disk space ({2}%)".format(device, mount_point, used)

Output::

    /dev/sda1 (/) ran out of disk space (86%)
    /dev/sda2 (/mnt/data) ran out of disk space (95%)


Documentation
-------------

Complete documentation is available at https://konishchevdmitry.github.io/psh/
