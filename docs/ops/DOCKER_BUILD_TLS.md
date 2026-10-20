# Docker build TLS trust

Docker builds keep normal certificate verification enabled. If the host uses
an approved TLS inspection CA that the Linux image does not trust, export only
that public CA certificate as PEM and set `ZMI_DOCKER_CA_CERT` to its path
before running `scripts/docker_gate.py docker-build` or `docker compose build`.
BuildKit mounts it only during dependency installation; the resulting image
trusts that CA for later HTTPS requests. The private signing key is never used
or copied. Do not commit a machine-specific trust anchor.

When unset, builds use the optional empty certificate input and the image's
standard CA bundle. Certificate verification is never disabled.
