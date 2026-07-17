# root-protection classic dnf (dnf4) plugin
# path: /usr/lib/python3.X/site-packages/dnf-plugins/root_protection.py

from dnfpluginscore import logger
import dnf
import os
import subprocess


class RootProtection(dnf.Plugin):
    name = "root_protection"

    def __init__(self, base, cli):
        super(RootProtection, self).__init__(base, cli)
        self.base = base
        self._hook = "/usr/libexec/root-protection/dnf-hook"

    def _run(self, phase):
        if not os.path.exists(self._hook):
            return
        try:
            subprocess.run([self._hook, phase], check=False)
        except Exception as e:
            logger.warning("root-protection dnf hook %s failed: %s", phase, e)

    def pre_transaction(self):
        self._run("pre")

    def transaction(self):
        self._run("post")
