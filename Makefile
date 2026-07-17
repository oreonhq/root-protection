PREFIX ?= /usr
SYSCONFDIR ?= /etc
UNITDIR ?= /usr/lib/systemd/system
LIBEXECDIR ?= /usr/libexec
PYTHON ?= python3
# force /usr prefix so RPM/make install does not land in /usr/local
PYSITE ?= $(shell $(PYTHON) -c 'import sysconfig; print(sysconfig.get_path("purelib", "posix_prefix", {"base":"/usr","platbase":"/usr"}))')

.PHONY: all install uninstall check test

all:
	@echo "use: make install DESTDIR=..."

install:
	install -d $(DESTDIR)$(PREFIX)/bin
	install -d $(DESTDIR)$(PREFIX)/lib/root-protection/rpctl
	install -d $(DESTDIR)$(SYSCONFDIR)/root-protection
	install -d $(DESTDIR)$(PREFIX)/share/root-protection
	install -d $(DESTDIR)$(PREFIX)/share/doc/root-protection
	install -d $(DESTDIR)$(UNITDIR)
	install -d $(DESTDIR)$(LIBEXECDIR)/root-protection
	install -d $(DESTDIR)$(SYSCONFDIR)/profile.d
	install -d $(DESTDIR)$(SYSCONFDIR)/dnf/libdnf5-plugins/actions.d
	install -d $(DESTDIR)$(SYSCONFDIR)/dnf/plugins
	install -d $(DESTDIR)$(PYSITE)/dnf-plugins
	install -d $(DESTDIR)/var/lib/root-protection
	install -d $(DESTDIR)/var/log/root-protection

	install -m 0644 src/rpctl/*.py $(DESTDIR)$(PREFIX)/lib/root-protection/rpctl/
	install -m 0755 src/root-protection $(DESTDIR)$(PREFIX)/lib/root-protection/root-protection.py
	printf '%s\n' '#!/bin/sh' \
		'export PYTHONPATH="$(PREFIX)/lib/root-protection"' \
		'exec $(PYTHON) -B $(PREFIX)/lib/root-protection/root-protection.py "$$@"' \
		> $(DESTDIR)$(PREFIX)/bin/root-protection
	chmod 0755 $(DESTDIR)$(PREFIX)/bin/root-protection

	install -m 0644 config/config.toml $(DESTDIR)$(SYSCONFDIR)/root-protection/config.toml
	install -m 0644 config/config.toml $(DESTDIR)$(PREFIX)/share/root-protection/config.toml

	install -m 0644 systemd/*.service $(DESTDIR)$(UNITDIR)/
	install -m 0644 systemd/*.timer $(DESTDIR)$(UNITDIR)/

	install -m 0755 hooks/dnf5/dnf-hook $(DESTDIR)$(LIBEXECDIR)/root-protection/dnf-hook
	install -d $(DESTDIR)/boot/root-protection/bls
	install -m 0755 hooks/dnf5/ensure-boom-profile $(DESTDIR)$(LIBEXECDIR)/root-protection/ensure-boom-profile
	install -m 0755 hooks/dnf5/boom-create-entry $(DESTDIR)$(LIBEXECDIR)/root-protection/boom-create-entry
	install -m 0755 hooks/dnf5/restore-grub-default $(DESTDIR)$(LIBEXECDIR)/root-protection/restore-grub-default
	install -m 0755 hooks/dnf5/fix-grub-layout $(DESTDIR)$(LIBEXECDIR)/root-protection/fix-grub-layout
	install -m 0755 hooks/dnf5/emergency-fix-grub.sh $(DESTDIR)$(LIBEXECDIR)/root-protection/emergency-fix-grub.sh
	install -d $(DESTDIR)/etc/grub.d
	install -m 0755 grub/42_root-protection $(DESTDIR)/etc/grub.d/42_root-protection
	install -m 0644 hooks/dnf5/rp-conf-get.awk $(DESTDIR)$(LIBEXECDIR)/root-protection/rp-conf-get.awk
	install -m 0644 hooks/dnf5/root-protection.actions $(DESTDIR)$(SYSCONFDIR)/dnf/libdnf5-plugins/actions.d/root-protection.actions
	rm -rf $(DESTDIR)$(PREFIX)/lib/root-protection/rpctl/__pycache__
	printf '%s\n' '1.0.8' > $(DESTDIR)$(PREFIX)/lib/root-protection/VERSION

	install -m 0644 hooks/dnf/root_protection.py $(DESTDIR)$(PYSITE)/dnf-plugins/root_protection.py
	install -m 0644 hooks/dnf/root_protection.conf $(DESTDIR)$(SYSCONFDIR)/dnf/plugins/root_protection.conf

	install -m 0644 guard/root-protection-guard.sh $(DESTDIR)$(SYSCONFDIR)/profile.d/root-protection-guard.sh
	install -m 0644 guard/patterns.toml $(DESTDIR)$(SYSCONFDIR)/root-protection/patterns.toml
	install -m 0644 guard/guard-lib.sh $(DESTDIR)$(LIBEXECDIR)/root-protection/guard-lib.sh
	install -d $(DESTDIR)/usr/local/bin
	install -m 0755 guard/sudo-wrapper.sh $(DESTDIR)/usr/local/bin/sudo

	install -m 0644 docs/*.md $(DESTDIR)$(PREFIX)/share/doc/root-protection/
	install -m 0644 README.md $(DESTDIR)$(PREFIX)/share/doc/root-protection/README.md

check:
	$(PYTHON) -m py_compile src/rpctl/*.py src/root-protection
	$(PYTHON) -m unittest discover -s tests -v

test: check
