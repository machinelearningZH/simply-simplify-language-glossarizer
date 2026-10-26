# Maintenance notes

## eMudhra/emSign certificate update (2026-10-26)

The seven-day uv cooldown blocked certifi 2026.10.19 because its files were
uploaded on October 20, despite the version's October 19 date. The project
retains the global cooldown, exempts certifi for this emergency, and constrains
it to >=2026.10.19 to prevent rollback. Review removal of the package exemption
after October 27 once both release files have aged seven days.
See https://discuss.python.org/t/information-for-python-users-regarding-emudhra-emsign-ca-certificate-security-incident/109576.
