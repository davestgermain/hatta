install:
	python setup.py install

test:
	pytest tests/

locale-extract:
	pybabel extract --mapping=babel.ini --project='Hatta Wiki' --copyright-holder='Radomir Dopieralski' --msgid-bugs-address='hatta@sheep.art.pl' --output=locale/hatta.pot hatta/

locale-compile: locale/*/LC_MESSAGES/hatta.mo

locale/%/LC_MESSAGES/hatta.mo: locale/%/hatta.po
	msgfmt -o $@ -- $<

.PHONY: locale-extract locale-compile test install
