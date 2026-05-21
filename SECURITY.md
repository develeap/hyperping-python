# Security Policy

## Supported Versions

We release patches for security vulnerabilities for the following versions:

| Version | Supported          |
| ------- | ------------------ |
| 1.7.x   | :white_check_mark: |
| 1.6.x   | :white_check_mark: |
| < 1.6   | :x:                |

Older releases may receive a fix at maintainers' discretion when the issue is severe and an upgrade is not feasible. The latest 1.x release is always the recommended target.

## Reporting a Vulnerability

**Please do not report security vulnerabilities through public GitHub issues.**

Instead, please report security vulnerabilities by emailing:

**security@develeap.com**

You should receive a response within 48 hours. If for some reason you do not, please follow up via email to ensure we received your original message.

Please include the following information in your report:

- Type of vulnerability (e.g., credential exposure, request smuggling, deserialization issue, etc.)
- Full paths of source file(s) related to the vulnerability
- The location of the affected source code (tag/branch/commit or direct URL)
- Step-by-step instructions to reproduce the issue
- Proof-of-concept or exploit code (if possible)
- Impact of the issue, including how an attacker might exploit it
- The Python version, `hyperping` package version, and any relevant transitive dependency versions (`pip show hyperping`, `python --version`)

This information will help us triage your report more quickly.

## Preferred Languages

We prefer all communications to be in English.

## Security Update Process

1. The security report is received and assigned a primary handler
2. The problem is confirmed and a list of affected versions determined
3. Code is audited to find any potential similar problems
4. Fixes are prepared for all supported releases
5. New versions are released to PyPI as soon as possible, and a GitHub Security Advisory is published

## Public Disclosure

We believe in responsible disclosure. We will coordinate the public disclosure with you, and we prefer to fully disclose the vulnerability once a patch is available on PyPI.

## Comments on this Policy

If you have suggestions on how this process could be improved, please submit a pull request or open an issue to discuss.

---

**Thank you for helping keep hyperping-python and our users safe!**
